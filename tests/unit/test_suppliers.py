"""Suppliers module tests (spec 003 M5, T-017 directory + T-018/AC13 overdue).

AC13: an overdue supplier check-in (no recorded reply within the configured
window) surfaces as an attention item computed from stored data, with no message
sent. A supplier with no recorded check-in yet is NOT overdue (no false alarm on
a freshly added supplier). The directory and the signal are the OWNER's lens;
the supplier two-rooms self-service is M6.
"""
from datetime import date

import pytest

from backend.repositories.supplier_repository import SupplierRepository
from backend.services.supplier_service import SupplierService
from backend.modules.providers import proveedores_module
from backend.modules.protocol import Severity

TODAY = date(2026, 10, 13)


def _seed(conn, name, country=None, contact=None, last_checkin_at=None, is_active=1):
    conn.execute(
        "INSERT INTO suppliers (name, country, contact, is_active, last_checkin_at) VALUES (?, ?, ?, ?, ?)",
        (name, country, contact, is_active, last_checkin_at),
    )


# ------------------------------------------------------------------ directory

@pytest.mark.unit
@pytest.mark.database
def test_directory_lists_active_suppliers(test_db):
    import database

    with database.get_conn() as conn:
        _seed(conn, "Café del Valle", "Colombia", "+57 300")
        _seed(conn, "Maderas Armenia", "Armenia-Colombia")
        _seed(conn, "Inactivo SA", is_active=0)

    svc = SupplierService()
    names = [s.name for s in svc.directory(today=TODAY)]
    assert names == ["Café del Valle", "Maderas Armenia"]  # active only, name-ordered
    assert svc.count_active() == 2


# --------------------------------------------------------- overdue (AC13)

@pytest.mark.unit
@pytest.mark.database
def test_overdue_only_for_old_checkins(test_db):
    import database

    with database.get_conn() as conn:
        _seed(conn, "Atrasado", last_checkin_at="2026-09-01")   # 42 days -> overdue
        _seed(conn, "Reciente", last_checkin_at="2026-10-10")   # 3 days -> not overdue
        _seed(conn, "SinCheckin", last_checkin_at=None)         # never -> not overdue

    svc = SupplierService(window_days=14)
    overdue = {s.name for s in svc.overdue_checkins(today=TODAY)}
    assert overdue == {"Atrasado"}


@pytest.mark.unit
@pytest.mark.database
def test_overdue_computes_from_stored_data_no_message(test_db):
    """AC13: the signal is derived from stored data; nothing is sent. We assert
    the overdue list reflects stored dates and the supplier rows are unchanged."""
    import database

    with database.get_conn() as conn:
        _seed(conn, "Atrasado", last_checkin_at="2026-08-01")

    svc = SupplierService(window_days=14)
    before = svc.repository.list_suppliers()
    overdue = svc.overdue_checkins(today=TODAY)
    after = svc.repository.list_suppliers()
    assert len(overdue) == 1 and overdue[0].days_since_checkin == 73
    # No row mutated by reading the signal (no send, no state change).
    assert [dict(r) for r in before] == [dict(r) for r in after]


@pytest.mark.unit
@pytest.mark.database
def test_write_paths(test_db):
    import database

    repo = SupplierRepository()
    with database.get_conn():
        sid = repo.record_supplier(name="Nuevo Proveedor", country="Costa Rica", contact="x@y.com")
        repo.set_checkin(sid, "2026-10-12")
    rows = {r["name"]: r for r in repo.list_suppliers()}
    assert rows["Nuevo Proveedor"]["last_checkin_at"] == "2026-10-12"
    assert rows["Nuevo Proveedor"]["country"] == "Costa Rica"


# ----------------------------------------------------------- module snapshot

@pytest.mark.unit
def test_tile_and_overdue_attention():
    from backend.services.supplier_service import SupplierStatus

    directory = [
        SupplierStatus(1, "Atrasado", "Colombia", None, True, "2026-09-01", True, 42),
        SupplierStatus(2, "Al día", "Costa Rica", None, True, "2026-10-10", False, 3),
    ]
    snap = proveedores_module.compute_snapshot(directory, "123")
    assert snap.headline.value == "2"
    assert snap.headline.trend_tone == "warn"
    assert len(snap.attention) == 1
    assert snap.attention[0].severity == Severity.MID
    assert "Atrasado" in snap.attention[0].text


@pytest.mark.unit
def test_tile_empty_when_no_suppliers():
    snap = proveedores_module.compute_snapshot([], "123")
    assert snap.headline.status == "empty"
    assert snap.attention == []


@pytest.mark.unit
def test_tile_al_dia_when_none_overdue():
    from backend.services.supplier_service import SupplierStatus

    directory = [SupplierStatus(1, "X", None, None, True, "2026-10-12", False, 1)]
    snap = proveedores_module.compute_snapshot(directory, "123")
    assert snap.headline.trend == "al día"
    assert snap.headline.trend_tone == "good"
    assert snap.attention == []
