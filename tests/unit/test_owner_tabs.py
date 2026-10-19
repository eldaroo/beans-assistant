"""Owner-facing three-tab rail (spec 006 M1, AC1).

`nav.owner_tabs()` returns exactly three tabs — Hoy, Operación, Costos y
producción — derived off the module registry `group` field. The two module-group
tabs together cover all eight modules. Adding a module with a new `group` places
it in a new tab with no template edit (the AC1 reversibility promise), proven by
registering a throwaway module and seeing its tab appear.
"""
from __future__ import annotations

import pytest

from backend.modules import nav, registry
from backend.modules.protocol import AttentionItem, Headline, Module, ModuleSnapshot


def _blank_snapshot(_phone):  # a provider that never runs in these pure tests
    return ModuleSnapshot(headline=Headline(value="0"), attention=[])


def test_owner_tabs_returns_three_tabs():
    tabs = nav.owner_tabs()
    assert [t.id for t in tabs] == ["hoy", "operacion", "costos"]
    assert [t.label for t in tabs] == ["Hoy", "Operación", "Costos y producción"]


def test_hoy_is_the_first_overview_tab_with_no_owned_modules():
    tabs = nav.owner_tabs()
    hoy = tabs[0]
    assert hoy.id == nav.HOY_ID == "hoy"
    assert hoy.items == []
    assert hoy.count == 0


def test_three_tabs_cover_all_eight_modules():
    tabs = nav.owner_tabs()
    covered = {item.module_id for tab in tabs for item in tab.items}
    all_ids = {m.id for m in registry.all_modules()}
    assert len(all_ids) == 8
    assert covered == all_ids


def test_operacion_and_costos_hold_the_expected_modules():
    by_id = {t.id: t for t in nav.owner_tabs()}
    assert [i.module_id for i in by_id["operacion"].items] == ["caja", "productos", "stock", "ventas"]
    assert [i.module_id for i in by_id["costos"].items] == ["costos", "produccion", "logistica", "proveedores"]
    # Each tab's count equals its item length (what the rail badge shows).
    assert by_id["operacion"].count == 4
    assert by_id["costos"].count == 4


def test_a_new_group_adds_a_tab_with_no_template_edit(monkeypatch):
    """AC1: adding a `group` to a new Module descriptor places it in that tab with
    no template edit. owner_tabs() derives tabs from the registry, so a module in a
    brand-new group yields a brand-new tab, slugged from the group label."""
    extra = Module(
        id="marketing",
        label="Marketing",
        route="/marketing/{phone}",
        snapshot=_blank_snapshot,
        group="Crecimiento",
        order=200,
    )
    monkeypatch.setattr(registry, "all_modules", lambda: registry._MODULES + [extra])
    tabs = nav.owner_tabs()
    ids = [t.id for t in tabs]
    assert "crecimiento" in ids, "a module in a new group must surface as its own tab"
    crecimiento = next(t for t in tabs if t.id == "crecimiento")
    assert [i.module_id for i in crecimiento.items] == ["marketing"]
    # The existing three tabs are untouched.
    assert ids[:3] == ["hoy", "operacion", "costos"]


def test_a_module_with_no_group_falls_back_to_operacion(monkeypatch):
    ungrouped = Module(
        id="loose",
        label="Suelto",
        route="/loose/{phone}",
        snapshot=_blank_snapshot,
        group="",
        order=5,
    )
    monkeypatch.setattr(registry, "all_modules", lambda: [ungrouped] + registry._MODULES)
    by_id = {t.id: t for t in nav.owner_tabs()}
    assert "loose" in {i.module_id for i in by_id["operacion"].items}


def test_tab_id_for_module_maps_to_the_owning_tab():
    assert nav.tab_id_for_module("caja") == "operacion"
    assert nav.tab_id_for_module("ventas") == "operacion"
    assert nav.tab_id_for_module("costos") == "costos"
    assert nav.tab_id_for_module("proveedores") == "costos"
    # Unknown id never leaves a page with no tab selected.
    assert nav.tab_id_for_module("does-not-exist") == "hoy"
