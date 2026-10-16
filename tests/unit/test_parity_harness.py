"""Unit tests for the parity harness (spec 005, M5). The live Gemini-vs-gateway run is
external-deferred; these prove the model-free scoring and the >= decision with stub predictors,
plus that the fixtures file and the runner's dry-run wire together."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.eval.parity.harness import accuracy, parity_report, compare_backends  # noqa: E402


CASES = [{"id": f"c{i}", "input": f"in{i}"} for i in range(4)]


def test_accuracy_empty_is_zero():
    assert accuracy([], lambda c: True) == 0.0


def test_accuracy_fraction():
    # pass c0 and c2 only
    assert accuracy(CASES, lambda c: c["id"] in {"c0", "c2"}) == 0.5


def test_parity_ok_when_gateway_beats_gemini():
    r = parity_report(0.8, 0.9)
    assert r["parity_ok"] is True
    assert r["delta"] == 0.1


def test_parity_ok_when_equal():
    assert parity_report(0.9, 0.9)["parity_ok"] is True


def test_parity_fails_on_regression_beyond_tolerance():
    assert parity_report(0.9, 0.8)["parity_ok"] is False
    # within a tolerance band it passes
    assert parity_report(0.9, 0.8, tolerance=0.15)["parity_ok"] is True


def test_compare_backends_flags_regressions():
    gemini = lambda c: True  # Gemini passes all
    gateway = lambda c: c["id"] != "c1"  # Claude misses c1
    r = compare_backends(CASES, gemini, gateway)
    assert r["n"] == 4
    assert r["gemini_accuracy"] == 1.0
    assert r["gateway_accuracy"] == 0.75
    assert r["parity_ok"] is False
    assert [x["id"] for x in r["regressions"]] == ["c1"]


def test_fixtures_file_is_valid_and_cross_domain():
    fx = json.loads((ROOT / "tests" / "eval" / "parity" / "fixtures.json").read_text(encoding="utf-8"))
    agents = {c["agent"] for c in fx["cases"]}
    assert {"router", "resolver", "read"}.issubset(agents)
    assert len(fx["cases"]) >= 6


def test_runner_dry_run_passes_offline():
    # The dry-run exercises the full compare pipeline with no models and must report parity_ok.
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "eval" / "parity" / "run_parity.py"), "--dry-run"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "parity_ok=True" in proc.stdout
