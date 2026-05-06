"""
Resolver eval runner — M3a (deterministic) + M3b (LLM hybrid).

Loads tests/eval/resolver/golden.json, builds a synthetic AgentState per
case, invokes create_resolver_agent against a fresh SQLite catalog
(schema from root_archive/init_complete_database.sql plus
tests/eval/resolver/fixtures/catalog.sql), and scores per-case.

Modes (--llm flag):
  --llm none    (default) Skip cases marked llm_required: true. Run
                deterministic baseline only. No GOOGLE_API_KEY needed.
  --llm gemini  Run all cases. Requires GOOGLE_API_KEY in env. Forces
                GEMINI_TEMPERATURE=0 for run-to-run stability (mirrors
                the router runner). Uses get_llm_cheap() — same factory
                as prod (graph.py:45).

Scoring dimensions (each case opts into the ones it asserts):
  - items_resolved_match: every expected item's resolved_sku /
    resolved_sku_in / has_resolution_error matches by position.

Output (mirrors router run_eval.py for diff parity):
  - stdout: per-case ok/fail lines + summary block
  - tests/eval/resolver/results/eval-<UTC-timestamp>.json: artifact

Usage (from beans-assistant repo root):
    python tests/eval/resolver/run_eval.py
    python tests/eval/resolver/run_eval.py --n-runs 3 --threshold 100
    python tests/eval/resolver/run_eval.py --llm gemini --n-runs 3 --threshold 80
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO_ROOT / "tests" / "eval" / "resolver"
RESULTS_DIR = EVAL_DIR / "results"
GOLDEN_FILE = EVAL_DIR / "golden.json"
SCHEMA_FILE = REPO_ROOT / "root_archive" / "init_complete_database.sql"
CATALOG_FIXTURE = EVAL_DIR / "fixtures" / "catalog.sql"


def _setup_test_db(tmp_dir: Path) -> Path:
    """Create a fresh SQLite DB in tmp_dir, seeded with full schema +
    catalog fixture. Returns the path."""
    db_path = tmp_dir / "resolver-eval.db"
    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    fixture_sql = CATALOG_FIXTURE.read_text(encoding="utf-8")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(schema_sql)
    conn.executescript(fixture_sql)
    conn.commit()
    conn.close()
    return db_path


def _load_cases(use_llm: bool) -> list[dict[str, Any]]:
    """Filter by `mode`: 'deterministic' runs only with --llm none,
    'llm' runs only with --llm gemini, missing/'both' runs always."""
    if not GOLDEN_FILE.exists():
        raise RuntimeError(f"Golden file not found: {GOLDEN_FILE}")
    with GOLDEN_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    cases = []
    for raw in data.get("cases", []):
        mode = raw.get("mode", "both")
        if mode == "llm" and not use_llm:
            continue
        if mode == "deterministic" and use_llm:
            continue
        cases.append({
            "id": raw.get("id") or "<unnamed>",
            "category": raw.get("category"),
            "difficulty": raw.get("difficulty"),
            "mode": mode,
            "input": raw["input"],
            "expected": raw["expected"],
        })
    if not cases:
        raise RuntimeError("Golden file has zero cases (after filtering)")
    return cases


def _score_items(expected_items: list, actual_items: list) -> bool:
    """Positional comparison. Each expected item asserts one of:
      - has_resolution_error: true               -> resolution_error must be set
      - resolved_sku: "X"                        -> exact sku match
      - resolved_sku_in: ["A", "B", ...]         -> sku must be in the list
      - resolved_name_contains: "..."            -> substring in resolved_name
    Extra fields in actual are ignored."""
    if not isinstance(actual_items, list) or len(actual_items) != len(expected_items):
        return False
    for e, a in zip(expected_items, actual_items):
        if e.get("has_resolution_error"):
            if "resolution_error" not in a:
                return False
        elif "resolved_sku" in e:
            if a.get("resolved_sku") != e["resolved_sku"]:
                return False
        elif "resolved_sku_in" in e:
            if a.get("resolved_sku") not in e["resolved_sku_in"]:
                return False
        elif "resolved_name_contains" in e:
            name = a.get("resolved_name") or ""
            if e["resolved_name_contains"] not in name:
                return False
    return True


def _score_case(expected: dict[str, Any], result_entities: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    if "items" in expected:
        actual_items = result_entities.get("items") or []
        out["items_resolved_match"] = _score_items(expected["items"], actual_items)
    else:
        out["items_resolved_match"] = None

    if "resolved_sku" in expected:
        out["top_level_resolved_match"] = (
            result_entities.get("resolved_sku") == expected["resolved_sku"]
        )
    elif "has_resolution_error" in expected:
        out["top_level_resolved_match"] = (
            ("resolution_error" in result_entities) == expected["has_resolution_error"]
        )
    else:
        out["top_level_resolved_match"] = None

    asserted = [v for v in out.values() if v is not None]
    out["overall_pass"] = bool(asserted) and all(asserted)
    return out


def _build_state(case_input: dict[str, Any]) -> dict[str, Any]:
    """Assemble the minimal AgentState the resolver expects."""
    return {
        "messages": [],
        "user_input": case_input.get("user_input", ""),
        "phone": "+5491100000000",
        "sender": "+5491100000000",
        "intent": None,
        "operation_type": case_input.get("operation_type"),
        "confidence": None,
        "missing_fields": [],
        "normalized_entities": case_input.get("normalized_entities", {}),
        "sql_result": None,
        "operation_result": None,
        "final_answer": None,
        "error": None,
        "next_action": None,
        "metadata": {},
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolver eval runner.")
    parser.add_argument(
        "--n-runs", type=int, default=1,
        help="Invoke each case N times (default 1). Deterministic cases "
             "barely benefit from N>1; LLM cases need it for stability."
    )
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Minimum overall_pass rate (0-100) below which the runner "
             "exits with code 2."
    )
    parser.add_argument(
        "--llm", choices=("none", "gemini"), default="none",
        help="'none' (default) skips llm_required cases. 'gemini' loads "
             "get_llm_cheap() (Gemini 2.5 Flash) and runs all cases. "
             "Requires GOOGLE_API_KEY in env."
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    n_runs = max(1, args.n_runs)
    use_llm = args.llm == "gemini"

    sys.path.insert(0, str(REPO_ROOT))
    import os
    import tempfile

    if use_llm:
        # Force temperature=0 BEFORE importing llm.py — same discipline as
        # tests/eval/router/run_eval.py. The factory reads the env var.
        os.environ["GEMINI_TEMPERATURE"] = "0"
        if not os.getenv("GOOGLE_API_KEY"):
            print("ERROR: --llm gemini requires GOOGLE_API_KEY in environment.", file=sys.stderr)
            return 3

    import database
    from agents.resolver import create_resolver_agent

    llm = None
    if use_llm:
        from llm import get_llm_cheap
        llm = get_llm_cheap()

    tmp_dir = Path(tempfile.mkdtemp(prefix="resolver-eval-"))
    db_path = _setup_test_db(tmp_dir)
    db_path_token = database.set_tenant_db_path(str(db_path))

    try:
        resolve_entities = create_resolver_agent(llm=llm)

        cases = _load_cases(use_llm=use_llm)
        by_mode = {"deterministic": 0, "llm": 0, "both": 0}
        for c in cases:
            by_mode[c["mode"]] = by_mode.get(c["mode"], 0) + 1
        print(f"Loaded {len(cases)} cases from {GOLDEN_FILE.name} "
              f"(mode: {by_mode['both']} both, {by_mode['deterministic']} det-only, {by_mode['llm']} llm-only).")
        print(f"Mode: --llm={args.llm}"
              + (f"  GEMINI_MODEL={os.getenv('GEMINI_MODEL', '<default>')}"
                 f"  GEMINI_TEMPERATURE={os.getenv('GEMINI_TEMPERATURE')}" if use_llm else ""))
        print(f"DB fixture: {db_path}  N={n_runs}")
        print()

        started_at = datetime.now(timezone.utc)
        t0 = time.perf_counter()

        per_case: list[dict[str, Any]] = []
        counters = {
            "items_resolved_match": [0, 0],
            "top_level_resolved_match": [0, 0],
            "overall": [0, 0],
            "errors": 0,
        }
        unstable_ids: list[str] = []

        for idx, case in enumerate(cases, start=1):
            case_id = case["id"]
            runs: list[dict[str, Any]] = []
            case_passes = 0
            had_error = False

            for run_i in range(n_runs):
                state = _build_state(case["input"])
                try:
                    t_case = time.perf_counter()
                    result = resolve_entities(state)
                    elapsed_ms = round((time.perf_counter() - t_case) * 1000, 1)
                except Exception as exc:
                    counters["errors"] += 1
                    had_error = True
                    runs.append({
                        "run": run_i + 1,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    })
                    continue

                result_entities = result.get("normalized_entities") or {}
                score = _score_case(case["expected"], result_entities)

                for dim in ("items_resolved_match", "top_level_resolved_match"):
                    if score[dim] is not None:
                        counters[dim][1] += 1
                        if score[dim]:
                            counters[dim][0] += 1
                counters["overall"][1] += 1
                if score["overall_pass"]:
                    counters["overall"][0] += 1
                    case_passes += 1

                runs.append({
                    "run": run_i + 1,
                    "result_entities": result_entities,
                    "score": score,
                    "elapsed_ms": elapsed_ms,
                })

            if had_error:
                print(f"[{idx:02d}/{len(cases)}] ERROR  {case_id}")
            else:
                unstable = (n_runs > 1 and 0 < case_passes < n_runs)
                if unstable:
                    unstable_ids.append(case_id)
                if n_runs == 1:
                    flag = "ok  " if case_passes == 1 else "FAIL"
                    last = runs[-1]
                    print(f"[{idx:02d}/{len(cases)}] {flag} {case_id:<40} ({last.get('elapsed_ms')} ms)")
                else:
                    tag = "FLAKY" if unstable else ("ok   " if case_passes == n_runs else "FAIL ")
                    print(f"[{idx:02d}/{len(cases)}] {tag} {case_id:<40} agreement={case_passes}/{n_runs}")

            per_case.append({
                "id": case_id,
                "category": case["category"],
                "difficulty": case["difficulty"],
                "mode": case["mode"],
                "expected": case["expected"],
                "runs": runs,
                "agreement": case_passes / n_runs if not had_error else None,
                "unstable": (n_runs > 1 and 0 < case_passes < n_runs),
            })

        total_wall = round(time.perf_counter() - t0, 2)

        def _rate(pair: list[int]) -> str:
            passed, total = pair
            if total == 0:
                return "n/a"
            return f"{passed}/{total} ({100.0 * passed / total:.1f}%)"

        print()
        print("=" * 60)
        print(f"SUMMARY  ({len(cases)} cases x {n_runs} runs = "
              f"{len(cases) * n_runs} trials, {total_wall}s wall, {counters['errors']} errors)")
        print("-" * 60)
        print(f"  items_resolved_match       {_rate(counters['items_resolved_match'])}")
        print(f"  top_level_resolved_match   {_rate(counters['top_level_resolved_match'])}")
        print(f"  overall_pass               {_rate(counters['overall'])}")
        if n_runs > 1:
            print(f"  unstable cases             {len(unstable_ids)}"
                  + (f"  -> {', '.join(unstable_ids)}" if unstable_ids else ""))
        print("=" * 60)

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        artifact = RESULTS_DIR / f"eval-{started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
        with artifact.open("w", encoding="utf-8") as f:
            json.dump({
                "started_at": started_at.isoformat(),
                "wall_seconds": total_wall,
                "n_runs": n_runs,
                "llm_mode": args.llm,
                "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if use_llm else None,
                "temperature": os.getenv("GEMINI_TEMPERATURE") if use_llm else None,
                "totals": {
                    "cases": len(cases),
                    "trials": len(cases) * n_runs,
                    "errors": counters["errors"],
                    "items_resolved_match": counters["items_resolved_match"],
                    "top_level_resolved_match": counters["top_level_resolved_match"],
                    "overall": counters["overall"],
                    "unstable_case_ids": unstable_ids,
                },
                "cases": per_case,
            }, f, indent=2, ensure_ascii=False, default=str)
        print(f"Artifact: {artifact.relative_to(REPO_ROOT)}")

        if counters["errors"] > 0:
            return 1

        if args.threshold is not None:
            passed, total = counters["overall"]
            rate_pct = 100.0 * passed / total if total else 0.0
            if rate_pct < args.threshold:
                print(f"\nFAIL: overall_pass {rate_pct:.1f}% < threshold {args.threshold:.1f}%")
                return 2

        return 0

    finally:
        database.reset_tenant_db_path(db_path_token)
        # tmp_dir auto-cleans via OS, but be explicit if you care:
        # shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
