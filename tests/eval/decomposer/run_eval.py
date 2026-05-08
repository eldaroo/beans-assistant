"""
Decomposer eval runner (PR-B).

Loads the decomposer golden file (tests/eval/decomposer.json), invokes the
live decomposer node against each case in isolation, and scores per-case
along two dimensions:
  - gate_match         (should_decompose vs expected)
  - sub_inputs_match   (LLM-produced sub_inputs vs expected, exact list match
                        when the gate fires; pass-through case asserts a
                        single-element list equal to the original input)

Determinism: forces GEMINI_TEMPERATURE=0 in os.environ before importing the
project's llm module, per eval principle 6.

Stability (principle 7): with --n-runs N>1, each case is invoked N times and
agreement rate (passes / N) is reported per case. Cases with agreement < 1.0
are flagged as unstable in the artifact.

Usage (from beans-assistant repo root, with .env loaded):
    python tests/eval/decomposer/run_eval.py
    python tests/eval/decomposer/run_eval.py --n-runs 3
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
DECOMPOSER_EVAL_DIR = EVAL_DIR / "decomposer"
RESULTS_DIR = DECOMPOSER_EVAL_DIR / "results"

GOLDEN_FILE = EVAL_DIR / "decomposer.json"


def _force_deterministic_env() -> None:
    os.environ["GEMINI_TEMPERATURE"] = "0"
    os.environ["OPENAI_TEMPERATURE"] = "0"


def _load_cases() -> list[dict[str, Any]]:
    if not GOLDEN_FILE.exists():
        raise RuntimeError(f"Golden file not found: {GOLDEN_FILE}")
    with GOLDEN_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return [
        {
            "id": raw.get("name") or raw.get("id") or "<unnamed>",
            "category": raw.get("category"),
            "input": raw["input"],
            "context": raw.get("context"),
            "expected": raw["expected"],
        }
        for raw in data.get("cases", [])
    ]


def _invoke_decomposer(decompose, case_input: str) -> dict[str, Any]:
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
    return decompose(state)


def _score_case(
    expected: dict[str, Any],
    delta: dict[str, Any],
    case_input: str,
) -> dict[str, Any]:
    from agents.decomposer import should_decompose

    out: dict[str, Any] = {}

    actual_gate = should_decompose(case_input)
    out["gate_match"] = (actual_gate == expected["should_decompose"])

    metadata = delta.get("metadata") or {}
    actual_sub_inputs = list(metadata.get("sub_input_queue") or [])
    expected_sub_inputs = list(expected.get("sub_inputs") or [])
    out["sub_inputs_match"] = (actual_sub_inputs == expected_sub_inputs)

    out["actual_gate"] = actual_gate
    out["actual_sub_inputs"] = actual_sub_inputs

    asserted = [out["gate_match"], out["sub_inputs_match"]]
    out["overall_pass"] = all(asserted)
    return out


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decomposer eval runner.")
    parser.add_argument(
        "--n-runs", type=int, default=1,
        help="Invoke each case N times (default 1). N>1 reports per-case "
             "agreement rate; cases with agreement < 1.0 are flagged unstable."
    )
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Minimum overall_pass rate (0-100) below which the runner "
             "exits with code 2. Default: no threshold enforcement."
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    n_runs = max(1, args.n_runs)

    _force_deterministic_env()

    sys.path.insert(0, str(REPO_ROOT))
    from agents.decomposer import create_decomposer_agent
    from llm import get_llm_cheap

    llm = get_llm_cheap()
    decompose = create_decomposer_agent(llm)

    cases = _load_cases()
    print(f"Loaded {len(cases)} cases from {GOLDEN_FILE.relative_to(REPO_ROOT)}.")
    print(f"Model env: GEMINI_MODEL={os.getenv('GEMINI_MODEL', '<default>')} "
          f"GEMINI_TEMPERATURE={os.getenv('GEMINI_TEMPERATURE')}  N={n_runs}")
    print()

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    per_case: list[dict[str, Any]] = []
    counters = {
        "gate_match": [0, 0],
        "sub_inputs_match": [0, 0],
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
                delta = _invoke_decomposer(decompose, case["input"])
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

            score = _score_case(case["expected"], delta, case["input"])

            for dim in ("gate_match", "sub_inputs_match"):
                counters[dim][1] += 1
                if score[dim]:
                    counters[dim][0] += 1
            counters["overall"][1] += 1
            if score["overall_pass"]:
                counters["overall"][0] += 1
                case_passes += 1

            runs.append({
                "run": run_i + 1,
                "actual_gate": score["actual_gate"],
                "actual_sub_inputs": score["actual_sub_inputs"],
                "score": {
                    "gate_match": score["gate_match"],
                    "sub_inputs_match": score["sub_inputs_match"],
                    "overall_pass": score["overall_pass"],
                },
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
                print(f"[{idx:02d}/{len(cases)}] {flag} {case_id:<40} "
                      f"gate={last.get('actual_gate')} "
                      f"sub_inputs={last.get('actual_sub_inputs')} "
                      f"({last.get('elapsed_ms')} ms)")
            else:
                tag = "FLAKY" if unstable else (
                    "ok   " if case_passes == n_runs else "FAIL "
                )
                print(f"[{idx:02d}/{len(cases)}] {tag} {case_id:<40} "
                      f"agreement={case_passes}/{n_runs}")

        per_case.append({
            "id": case_id,
            "category": case["category"],
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
          f"{len(cases) * n_runs} trials, {total_wall}s wall, "
          f"{counters['errors']} errors)")
    print("-" * 60)
    print(f"  gate_match            {_rate(counters['gate_match'])}")
    print(f"  sub_inputs_match      {_rate(counters['sub_inputs_match'])}")
    print(f"  overall_pass          {_rate(counters['overall'])}")
    if n_runs > 1:
        print(f"  unstable cases        {len(unstable_ids)}"
              + (f"  -> {', '.join(unstable_ids)}" if unstable_ids else ""))
    print("=" * 60)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = RESULTS_DIR / f"eval-{started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    with artifact.open("w", encoding="utf-8") as f:
        json.dump({
            "started_at": started_at.isoformat(),
            "wall_seconds": total_wall,
            "model": os.getenv("GEMINI_CHEAP_MODEL")
                or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "temperature": os.getenv("GEMINI_TEMPERATURE"),
            "n_runs": n_runs,
            "totals": {
                "cases": len(cases),
                "trials": len(cases) * n_runs,
                "errors": counters["errors"],
                "gate_match": counters["gate_match"],
                "sub_inputs_match": counters["sub_inputs_match"],
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
            print(f"\nFAIL: overall_pass {rate_pct:.1f}% < threshold "
                  f"{args.threshold:.1f}%")
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
