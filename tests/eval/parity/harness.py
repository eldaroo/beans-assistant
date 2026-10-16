"""Parity harness (spec 005, M5) — pure, testable scoring for Gemini-vs-gateway comparison.

The LIVE parity run (invoking real agents under each backend) lives in run_parity.py and needs
the deployed gateway + a Gemini key, so it is external-deferred. These functions are the
model-free core: they score a set of cases under an injected predictor and decide whether the
Claude path meets or beats Gemini on the known set (spec acceptance 3)."""

from __future__ import annotations

from typing import Callable


def accuracy(cases: list, predict: Callable[[dict], bool]) -> float:
    """Fraction of cases the predictor passes. predict(case) -> bool."""
    if not cases:
        return 0.0
    passed = sum(1 for c in cases if predict(c))
    return passed / len(cases)


def parity_report(gemini_accuracy: float, gateway_accuracy: float, tolerance: float = 0.0) -> dict:
    """Decide parity: the gateway passes when it meets or beats Gemini within `tolerance`.

    tolerance is the allowed regression band (0.0 = the Claude path must be >= Gemini). delta is
    gateway minus gemini (positive = Claude did better)."""
    delta = round(gateway_accuracy - gemini_accuracy, 6)
    return {
        "gemini_accuracy": round(gemini_accuracy, 6),
        "gateway_accuracy": round(gateway_accuracy, 6),
        "delta": delta,
        "tolerance": tolerance,
        "parity_ok": gateway_accuracy >= gemini_accuracy - tolerance,
    }


def compare_backends(
    cases: list,
    gemini_predict: Callable[[dict], bool],
    gateway_predict: Callable[[dict], bool],
    tolerance: float = 0.0,
) -> dict:
    """Run both predictors over the same cases and produce a full parity report, including the
    per-case breakdown (both pass / only gemini / only gateway / neither) so a regression is
    traceable to the exact turns the Claude path handles differently."""
    rows = []
    gem_pass = gw_pass = 0
    for c in cases:
        g = bool(gemini_predict(c))
        w = bool(gateway_predict(c))
        gem_pass += g
        gw_pass += w
        rows.append({
            "id": c.get("id"),
            "input": c.get("input"),
            "gemini_pass": g,
            "gateway_pass": w,
            "regression": g and not w,  # Gemini got it, Claude missed it
        })
    n = len(cases) or 1
    report = parity_report(gem_pass / n, gw_pass / n, tolerance)
    report["n"] = len(cases)
    report["regressions"] = [r for r in rows if r["regression"]]
    report["cases"] = rows
    return report
