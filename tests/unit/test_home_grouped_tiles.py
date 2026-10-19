"""Grouped home tiles (spec 006 M1, AC6).

The home builds its tiles with ONE registry fan-out (``build_home``). The tabs
then slice that one result: Hoy shows every tile plus the attention strip, each
module-group tab shows only its own modules' tiles, and switching tabs never
triggers another fan-out (the slice is pure). These tests prove the slicing
(``home_service.tiles_by_tab``) and that each tile carries its ``group``.
"""
from __future__ import annotations

from backend.modules import home_service, nav
from backend.modules.protocol import ModuleTile


def _tile(module_id, value="1"):
    # The tiles carry no `group`; tiles_by_tab routes a tile to its tab by
    # module_id against nav.owner_tabs(), which reads the registry `group`.
    return ModuleTile(
        module_id=module_id,
        label=module_id.title(),
        route=f"/{module_id}/{{phone}}",
        value=value,
        trend=None,
        trend_tone="flat",
        status="ok",
    )


def _view():
    # Mirror the real registry order, with distinct values so a misrouted tile
    # would show up as a wrong number under a tab.
    tiles = [
        _tile("caja", "USD 3.7k"),
        _tile("productos", "12"),
        _tile("stock", "540 u"),
        _tile("ventas", "USD 1.9k"),
        _tile("costos", "USD 2.10"),
        _tile("produccion", "320 u"),
        _tile("logistica", "2 lanes"),
        _tile("proveedores", "3"),
    ]
    return home_service.HomeView(tiles=tiles, attention=[], rail_groups=[])


def test_hoy_tab_shows_every_tile():
    view = _view()
    tabs = nav.owner_tabs()
    grouped = home_service.tiles_by_tab(view, tabs)
    assert [t.module_id for t in grouped["hoy"]] == [t.module_id for t in view.tiles]


def test_operacion_tab_shows_only_its_group_tiles():
    view = _view()
    grouped = home_service.tiles_by_tab(view, nav.owner_tabs())
    assert [t.module_id for t in grouped["operacion"]] == ["caja", "productos", "stock", "ventas"]
    # the numbers are carried through unchanged
    assert [t.value for t in grouped["operacion"]] == ["USD 3.7k", "12", "540 u", "USD 1.9k"]


def test_costos_tab_shows_only_its_group_tiles():
    view = _view()
    grouped = home_service.tiles_by_tab(view, nav.owner_tabs())
    assert [t.module_id for t in grouped["costos"]] == ["costos", "produccion", "logistica", "proveedores"]


def test_no_tile_appears_under_two_module_tabs():
    view = _view()
    grouped = home_service.tiles_by_tab(view, nav.owner_tabs())
    op = {t.module_id for t in grouped["operacion"]}
    co = {t.module_id for t in grouped["costos"]}
    assert op.isdisjoint(co)
    assert op | co == {t.module_id for t in view.tiles}


def test_registry_modules_carry_their_tab_group():
    # The registry `group` field is what drives the grouping (via owner_tabs);
    # the tile viewmodel itself carries no group, so routing is by module_id.
    from backend.modules import registry

    groups = {m.id: m.group for m in registry.all_modules()}
    assert groups["caja"] == "Operación"
    assert groups["costos"] == "Costos y producción"
