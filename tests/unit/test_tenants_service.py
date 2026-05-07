"""Regression: TenantsService.get_tenant must not alias-resolve Argentine
+54 ↔ +549 phones. require_tenant_match upstream enforces strict equality
between session phone and URL phone, so any alias hop on the read side is
a cross-tenant leak.

See commit 682d57a, ADR none (security fix). Reproduced once: a session for
"+541153695627" (no mobile prefix, deleted tenant) saw the dashboard for
"+5491153695627" (different active tenant).
"""

import pytest

from backend.services.tenants_service import TenantNotFoundError, TenantsService


class _FakeRepository:
    """In-memory repository fake. Models the post-fix split between
    get_tenant_config (alias-resolving, WhatsApp path) and
    get_tenant_config_strict (exact match, portal path)."""

    def __init__(self, tenants_by_phone: dict):
        self._tenants = tenants_by_phone

    def get_tenant_config_strict(self, phone: str):
        return self._tenants.get(phone)

    def list_tenants(self):
        return [
            {**cfg, "phone_number": phone, "created_at": "2026-01-01", "status": "active"}
            for phone, cfg in self._tenants.items()
        ]


def test_get_tenant_strict_does_not_alias_argentine_mobile_prefix():
    """The bypass: session for '+541153695627' must not be served the
    '+5491153695627' tenant via alias resolution."""
    repo = _FakeRepository({
        "+5491153695627": {"business_name": "Juan Carlos Cafe", "currency": "ARS", "language": "es"},
    })
    svc = TenantsService(repository=repo)

    with pytest.raises(TenantNotFoundError):
        svc.get_tenant("+541153695627")


def test_get_tenant_returns_exact_match():
    """Positive control: the canonical phone returns the tenant."""
    repo = _FakeRepository({
        "+5491153695627": {"business_name": "Juan Carlos Cafe", "currency": "ARS", "language": "es"},
    })
    svc = TenantsService(repository=repo)

    result = svc.get_tenant("+5491153695627")

    assert result.phone_number == "+5491153695627"
    assert result.business_name == "Juan Carlos Cafe"


def test_get_tenant_strict_does_not_alias_reverse_direction():
    """Reverse direction: session for '+5491100000001' must not be served
    the '+541100000001' tenant. The fix must hold both ways."""
    repo = _FakeRepository({
        "+541100000001": {"business_name": "Landline Tenant", "currency": "USD", "language": "es"},
    })
    svc = TenantsService(repository=repo)

    with pytest.raises(TenantNotFoundError):
        svc.get_tenant("+5491100000001")
