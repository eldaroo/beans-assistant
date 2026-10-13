"""Control Center shell tests (M1): registry contract, fail-open, attention cap.

Pure tests over the single-provider protocol with no database: a module is a
descriptor with one ``snapshot(phone) -> ModuleSnapshot`` provider, and the
shell turns the registry into a home viewmodel.

Covers AC1 (a registered descriptor appears as a tile + strip item), AC3 (a
throwing OR slow provider degrades only its own tile without breaking the home),
AC4 (the attention service aggregates, sorts by severity, and caps the strip),
and the empty-vs-degraded home semantics.
"""
import time

import pytest

from backend.modules import attention_service, home_service
from backend.modules.attention_service import ATTENTION_CAP
from backend.modules.protocol import (
    STATUS_DEGRADED,
    STATUS_EMPTY,
    STATUS_OK,
    AttentionItem,
    Headline,
    Module,
    ModuleSnapshot,
    Severity,
)


def _mod(mid, *, value="1", trend=None, tone="flat", status=STATUS_OK, items=None, raises=False, sleep=0.0):
    def snapshot(_phone):
        if raises:
            raise RuntimeError(f"{mid} boom")
        if sleep:
            time.sleep(sleep)
        return ModuleSnapshot(
            headline=Headline(value=value, trend=trend, trend_tone=tone, status=status),
            attention=list(items or []),
        )

    return Module(id=mid, label=mid.title(), route=f"?tab={mid}", snapshot=snapshot)


# ---------------------------------------------------------------- AC1

def test_registered_module_appears_as_tile_and_attention_item():
    item = AttentionItem(severity=Severity.MID, text="fake necesita atención", action_label="Ver")
    fake = _mod("fake", value="USD 9.9k", trend="subió", tone="good", items=[item])

    view = home_service.build_home("+100", modules=[fake])

    tile = next(t for t in view.tiles if t.module_id == "fake")
    assert tile.value == "USD 9.9k" and tile.status == STATUS_OK
    assert tile.route == "?tab=fake"
    assert any("fake necesita atención" in a.text for a in view.attention)
    assert any(a.module_id == "fake" for a in view.attention)


# ---------------------------------------------------------------- AC3 (broken)

def test_throwing_snapshot_degrades_only_its_own_tile():
    good_a = _mod("good_a", value="10")
    broken = _mod("broken", raises=True)
    good_b = _mod("good_b", value="20")

    view = home_service.build_home("+100", modules=[good_a, broken, good_b])

    by_id = {t.module_id: t for t in view.tiles}
    assert len(view.tiles) == 3
    assert by_id["broken"].status == STATUS_DEGRADED and by_id["broken"].value == "—"
    assert by_id["good_a"].status == STATUS_OK and by_id["good_a"].value == "10"
    assert by_id["good_b"].status == STATUS_OK and by_id["good_b"].value == "20"


def test_throwing_snapshot_contributes_no_attention():
    item = AttentionItem(severity=Severity.HIGH, text="sigue vivo")
    good = _mod("good", items=[item])
    broken = _mod("broken", raises=True)

    view = home_service.build_home("+100", modules=[good, broken])
    assert [a.text for a in view.attention] == ["sigue vivo"]


# ---------------------------------------------------------------- AC3 (slow)

def test_slow_snapshot_degrades_via_timeout(monkeypatch):
    """A module slower than the timeout degrades to a tile; the fast module is
    unaffected AND build_home returns at the deadline rather than waiting out the
    slow worker (the 'slow' half of fail-open, risk 2)."""
    monkeypatch.setattr(home_service, "SNAPSHOT_TIMEOUT_S", 0.2)
    fast = _mod("fast", value="9")
    slow = _mod("slow", value="never", sleep=3.0)

    started = time.monotonic()
    view = home_service.build_home("+100", modules=[fast, slow])
    elapsed = time.monotonic() - started

    by_id = {t.module_id: t for t in view.tiles}
    assert by_id["fast"].status == STATUS_OK and by_id["fast"].value == "9"
    assert by_id["slow"].status == STATUS_DEGRADED
    # returned at the ~0.2s deadline, NOT after the 3s hung worker.
    assert elapsed < 1.5, f"build_home blocked on the slow worker ({elapsed:.2f}s)"


# ---------------------------------------------------------------- AC4

def test_attention_prioritized_by_severity_and_capped():
    raw = (
        [AttentionItem(severity=Severity.LOW, text=f"low{i}") for i in range(3)]
        + [AttentionItem(severity=Severity.HIGH, text=f"high{i}") for i in range(3)]
        + [AttentionItem(severity=Severity.MID, text=f"mid{i}") for i in range(3)]
    )
    out = attention_service.prioritize(raw)
    assert len(out) == ATTENTION_CAP
    sevs = [int(i.severity) for i in out]
    assert sevs == sorted(sevs)
    assert sum(1 for i in out if i.severity == Severity.HIGH) == 3
    assert all(i.severity != Severity.LOW for i in out[: ATTENTION_CAP - 1])


def test_aggregate_stamps_module_id_and_is_fail_open():
    out = attention_service.aggregate(
        [
            ("stock", [AttentionItem(severity=Severity.MID, text="m0"), AttentionItem(severity=Severity.MID, text="m1")]),
            ("broken", []),  # a failed module contributes nothing
            ("caja", [AttentionItem(severity=Severity.HIGH, text="h0")]),
        ],
        cap=10,
    )
    assert [i.text for i in out] == ["h0", "m0", "m1"]  # HIGH first, then stable
    assert {i.module_id for i in out} == {"stock", "caja"}


# ---------------------------------------------------------------- empty vs degraded

def test_home_is_empty_only_when_all_tiles_empty():
    view = home_service.build_home("+100", modules=[
        _mod("a", status=STATUS_EMPTY), _mod("b", status=STATUS_EMPTY),
    ])
    assert view.is_empty is True


def test_all_degraded_is_not_empty():
    """An all-degraded home renders its tiles (outage visible), not the welcome."""
    view = home_service.build_home("+100", modules=[_mod("a", raises=True), _mod("b", raises=True)])
    assert all(t.status == STATUS_DEGRADED for t in view.tiles)
    assert view.is_empty is False


def test_mixed_ok_and_empty_is_not_empty():
    view = home_service.build_home("+100", modules=[
        _mod("a", status=STATUS_OK, value="5"), _mod("b", status=STATUS_EMPTY),
    ])
    assert view.is_empty is False
