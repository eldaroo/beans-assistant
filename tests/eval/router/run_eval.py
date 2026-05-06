"""
Router eval runner — M1 baseline.

Loads two golden files (tests/eval/router_propose_confirm.json and
tests/eval/router/golden.json), invokes the live router agent against each
case, and scores per-case along three orthogonal dimensions:
  - intent_match
  - operation_type_match
  - entities_subset_match (every key in expected.entities exists in
    normalized_entities with an equal value; lists compared positionally)

Determinism: forces GEMINI_TEMPERATURE=0 in os.environ before importing the
project's llm module, per eval principle 6.

Stability (principle 7): with --n-runs N>1, each case is invoked N times and
agreement rate (passes / N) is reported per case. Cases with agreement < 1.0
are flagged as unstable in the artifact.

Output:
  - stdout: per-case ok/fail lines + summary block (totals, pass-rates per
    dimension, wall time)
  - tests/eval/router/results/eval-<UTC-timestamp>.json: machine-readable
    artifact with per-case detail (for diffing across runs)

Usage (from beans-assistant repo root, with .env loaded):
    python tests/eval/router/run_eval.py
    python tests/eval/router/run_eval.py --n-runs 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO_ROOT / "tests" / "eval"
ROUTER_EVAL_DIR = EVAL_DIR / "router"
RESULTS_DIR = ROUTER_EVAL_DIR / "results"

GOLDEN_FILES = [
    EVAL_DIR / "router_propose_confirm.json",
    ROUTER_EVAL_DIR / "golden.json",
]


def _force_deterministic_env() -> None:
    os.environ["GEMINI_TEMPERATURE"] = "0"
    os.environ["OPENAI_TEMPERATURE"] = "0"


def _load_cases() -> list[dict[str, Any]]:
    """Load cases from every known golden file that exists on disk.

    Missing files are skipped with a warning rather than failing the run:
    some golden files (e.g. router_propose_confirm.json) live behind
    unmerged feature branches and only appear once that feature ships.
    Always require at least one file loaded so silent zero-case runs
    cannot pass CI by accident.
    """
    cases: list[dict[str, Any]] = []
    loaded_paths: list[str] = []
    for path in GOLDEN_FILES:
        if not path.exists():
            print(f"WARN: golden file not found, skipping: {path.relative_to(REPO_ROOT)}")
            continue
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for raw in data.get("cases", []):
            cases.append({
                "id": raw.get("id") or raw.get("name") or "<unnamed>",
                "category": raw.get("category"),
                "difficulty": raw.get("difficulty"),
                "input": raw["input"],
                "expected": raw["expected"],
                "_source": path.name,
            })
        loaded_paths.append(path.name)

    if not loaded_paths:
        raise RuntimeError(
            f"No golden files found. Looked for: {[str(p) for p in GOLDEN_FILES]}"
        )
    return cases


def _entities_subset_match(expected: Any, actual: Any) -> bool:
    """Recursive subset check.

    For dicts: every key in `expected` must exist in `actual` with a matching
    value. Extra keys in `actual` are allowed.

    For lists: compared positionally — same length, each pair recursively
    matched. (The router emits items in a deterministic order under temp=0.)

    For scalars: equality, with int/float treated as equal when numerically
    equivalent ("10" stays as a string mismatch on purpose — the router
    must normalize numerics).
    """
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        for key, sub_expected in expected.items():
            if key not in actual:
                return False
            if not _entities_subset_match(sub_expected, actual[key]):
                return False
        return True

    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return False
        return all(
            _entities_subset_match(e, a) for e, a in zip(expected, actual)
        )

    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(expected) == float(actual)

    return expected == actual


def _score_case(expected: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Return per-dimension pass/skip and an overall pass flag.

    Skipped dimensions (assertion not present in expected) do not count
    against the rate. Negative assertions (`intent_not`, `operation_type_not`)
    are evaluated as their own pass/fail and combined into the same dimension.
    """
    out: dict[str, Any] = {}

    if "intent" in expected:
        out["intent_match"] = (result.get("intent") == expected["intent"])
    elif "intent_not" in expected:
        out["intent_match"] = (result.get("intent") != expected["intent_not"])
    else:
        out["intent_match"] = None  # not asserted

    if "operation_type" in expected:
        out["operation_type_match"] = (
            result.get("operation_type") == expected["operation_type"]
        )
    elif "operation_type_not" in expected:
        out["operation_type_match"] = (
            result.get("operation_type") != expected["operation_type_not"]
        )
    else:
        out["operation_type_match"] = None

    if "entities" in expected:
        out["entities_subset_match"] = _entities_subset_match(
            expected["entities"], result.get("normalized_entities", {})
        )
    else:
        out["entities_subset_match"] = None

    asserted = [v for v in out.values() if v is not None]
    out["overall_pass"] = bool(asserted) and all(asserted)
    return out


def _invoke_router(route_intent, case_input: str) -> dict[str, Any]:
    state = {
        "messages": [],
        "user_input": case_input,
        "phone": "+5491100000000",
        "sender": "+5491100000000",
        "intent": None,
        "operation_type": None,
        "confidence": None,
        "missing_fields": [],
        "normalized_entities": {},
        "sql_result": None,
        "operation_result": None,
        "final_answer": None,
        "error": None,
        "next_action": None,
        "metadata": {},
    }
    return route_intent(state)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Router eval runner.")
    parser.add_argument(
        "--n-runs", type=int, default=1,
        help="Invoke each case N times (default 1). N>1 reports per-case "
             "agreement rate; cases with agreement < 1.0 are flagged unstable."
    )
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Minimum overall_pass rate (0-100) below which the runner "
             "exits with code 2. Default: no threshold enforcement. "
             "PR CI uses 100; nightly typically omits this."
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    n_runs = max(1, args.n_runs)

    _force_deterministic_env()

    sys.path.insert(0, str(REPO_ROOT))
    from agents.router import create_router_agent
    from llm import get_llm

    llm = get_llm()
    route_intent = create_router_agent(llm)

    cases = _load_cases()
    print(f"Loaded {len(cases)} cases from {len(GOLDEN_FILES)} golden file(s).")
    print(f"Model env: GEMINI_MODEL={os.getenv('GEMINI_MODEL', '<default>')} GEMINI_TEMPERATURE={os.getenv('GEMINI_TEMPERATURE')}  N={n_runs}")
    print()

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    per_case: list[dict[str, Any]] = []
    # Trial-level counters (each run counts as one trial across cases).
    counters = {
        "intent_match": [0, 0],
        "operation_type_match": [0, 0],
        "entities_subset_match": [0, 0],
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
            try:
                t_case = time.perf_counter()
                result = _invoke_router(route_intent, case["input"])
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

            score = _score_case(case["expected"], result)

            for dim in ("intent_match", "operation_type_match", "entities_subset_match"):
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
                "intent": result.get("intent"),
                "operation_type": result.get("operation_type"),
                "confidence": result.get("confidence"),
                "normalized_entities": result.get("normalized_entities"),
                "score": score,
                "elapsed_ms": elapsed_ms,
            })

        if had_error:
            print(f"[{idx:02d}/{len(cases)}] ERROR  {case_id}")
        else:
            agreement = case_passes / n_runs
            unstable = (n_runs > 1 and 0 < case_passes < n_runs)
            if unstable:
                unstable_ids.append(case_id)
            if n_runs == 1:
                flag = "ok  " if case_passes == 1 else "FAIL"
                last = runs[-1]
                print(f"[{idx:02d}/{len(cases)}] {flag} {case_id:<40} "
                      f"intent={last.get('intent')} op={last.get('operation_type')} "
                      f"({last.get('elapsed_ms')} ms)")
            else:
                tag = "FLAKY" if unstable else ("ok   " if case_passes == n_runs else "FAIL ")
                print(f"[{idx:02d}/{len(cases)}] {tag} {case_id:<40} "
                      f"agreement={case_passes}/{n_runs}")

        per_case.append({
            "id": case_id,
            "source": case["_source"],
            "category": case["category"],
            "difficulty": case["difficulty"],
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
    print(f"  intent_match            {_rate(counters['intent_match'])}")
    print(f"  operation_type_match    {_rate(counters['operation_type_match'])}")
    print(f"  entities_subset_match   {_rate(counters['entities_subset_match'])}")
    print(f"  overall_pass            {_rate(counters['overall'])}")
    if n_runs > 1:
        print(f"  unstable cases          {len(unstable_ids)}"
              + (f"  → {', '.join(unstable_ids)}" if unstable_ids else ""))
    print("=" * 60)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = RESULTS_DIR / f"eval-{started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    with artifact.open("w", encoding="utf-8") as f:
        json.dump({
            "started_at": started_at.isoformat(),
            "wall_seconds": total_wall,
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "temperature": os.getenv("GEMINI_TEMPERATURE"),
            "n_runs": n_runs,
            "totals": {
                "cases": len(cases),
                "trials": len(cases) * n_runs,
                "errors": counters["errors"],
                "intent_match": counters["intent_match"],
                "operation_type_match": counters["operation_type_match"],
                "entities_subset_match": counters["entities_subset_match"],
                "overall": counters["overall"],
                "unstable_case_ids": unstable_ids,
            },
            "cases": per_case,
        }, f, indent=2, ensure_ascii=False)
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


if __name__ == "__main__":
    sys.exit(main())
