"""Parity runner (spec 005, M5) — run the Timonel agents under Gemini and under the gateway over
the parity fixtures and confirm the Claude path meets or beats Gemini (acceptance 3).

The LIVE comparison needs the deployed gateway (a dedicated beans token) AND a Gemini key, so it
is external-deferred. Offline, `--dry-run` exercises the full harness wiring with deterministic
stub predictors, so the pipeline is demonstrable with no models.

Usage:
    python tests/eval/parity/run_parity.py --dry-run        # offline, stub predictors
    python tests/eval/parity/run_parity.py                  # live: gemini vs gateway
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.eval.parity.harness import compare_backends  # noqa: E402


def load_fixtures() -> list[dict]:
    with FIXTURES.open("r", encoding="utf-8") as f:
        return json.load(f)["cases"]


def _score(case: dict, result: dict) -> bool:
    """A case passes when EVERY assertion present in `expected` matches the result. The router
    emits intent=WRITE_OPERATION with a separate operation_type (REGISTER_SALE etc.), so a sale
    fixture asserts operation_type, not intent — both are checked when both are present."""
    exp = case.get("expected", {})
    if not exp:
        return False
    ok = True
    if "intent" in exp:
        ok = ok and result.get("intent") == exp["intent"]
    if "operation_type" in exp:
        ok = ok and result.get("operation_type") == exp["operation_type"]
    if "query_type" in exp:
        ok = ok and result.get("query_type") == exp["query_type"]
    if "resolved" in exp:
        ok = ok and bool(result.get("resolved")) == bool(exp["resolved"])
    return ok


def build_live_predictor(backend: str):
    """Return predict(case)->bool that runs the right agent for a fixture under `backend`.

    Imports are done lazily and the backend env is set first so llm.get_llm dispatches correctly.
    This is the external-deferred path (needs the deployed gateway and/or a Gemini key)."""
    os.environ["TIMONEL_LLM_BACKEND"] = backend
    os.environ.setdefault("GEMINI_TEMPERATURE", "0")
    from agents.router import create_router_agent  # noqa: E402
    from llm import get_llm, get_llm_cheap  # noqa: E402

    route_intent = create_router_agent(get_llm())

    def predict(case: dict) -> bool:
        agent = case.get("agent")
        if agent == "router":
            state = {"messages": [], "user_input": case["input"], "normalized_entities": {}}
            try:
                return _score(case, route_intent(state) or {})
            except Exception:
                return False
        # resolver / read live wiring is part of the external-deferred live run; the harness and
        # the router path above prove the pipeline. The deferred issue tracks full live coverage.
        return False

    return predict


def main() -> int:
    ap = argparse.ArgumentParser(description="Timonel Gemini-vs-gateway parity runner.")
    ap.add_argument("--dry-run", action="store_true", help="offline: deterministic stub predictors")
    ap.add_argument("--tolerance", type=float, default=0.0, help="allowed regression band (0 = must be >=)")
    args = ap.parse_args()

    cases = load_fixtures()

    if args.dry_run:
        # Both backends pass everything deterministically — proves the harness wiring offline.
        gemini_predict = lambda c: True
        gateway_predict = lambda c: True
    else:
        gemini_predict = build_live_predictor("gemini")
        gateway_predict = build_live_predictor("gateway")

    report = compare_backends(cases, gemini_predict, gateway_predict, tolerance=args.tolerance)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print()
    print(f"gemini={report['gemini_accuracy']:.3f}  gateway={report['gateway_accuracy']:.3f}  "
          f"delta={report['delta']:+.3f}  parity_ok={report['parity_ok']}")
    if report["regressions"]:
        print("REGRESSIONS (Gemini passed, Claude missed):")
        for r in report["regressions"]:
            print(f"  - {r['id']}: {r['input']}")
    return 0 if report["parity_ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
