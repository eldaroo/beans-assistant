"""Owner-page navigation (spec 004, S1-shell).

cc_base.html renders the held rail from a ``nav`` context var. The home passes
its own ``view.rail_groups`` (already built from live snapshots). Every other
owner page (the migrated read-only pages, and the new CRUD pages that follow)
passes ``owner_rail(phone)``: the same module set, grouped the same way, in
registry order, but derived from the descriptors alone — no snapshot fan-out, so
a module page's rail never pays the home's per-module query cost.

``business_name`` resolves the tenant display name with a safe fallback for the
shell (title, rail brand, topbar). The home keeps its own resolver because it
additionally 404s a genuinely nonexistent tenant; a module page is already
owner-gated by ``require_tenant_match`` before it renders, so it only needs the
display name.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.modules import registry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NavItem:
    module_id: str
    label: str
    route: str


@dataclass(frozen=True)
class NavGroup:
    label: str
    items: list


def owner_rail(phone: str | None = None) -> "list[NavGroup]":
    """The held rail every owner page shows: one entry per registered module,
    grouped by ``rail_group``, in registry order. Derived from descriptors only.
    ``phone`` is accepted for signature symmetry with the home; the rail links
    are tenant-filled by cc_base's ``href_for`` at render time."""
    groups: dict[str, NavGroup] = {}
    order: list[str] = []
    for m in sorted(registry.all_modules(), key=lambda mod: mod.order):
        key = m.rail_group or ""
        if key not in groups:
            groups[key] = NavGroup(label=key, items=[])
            order.append(key)
        groups[key].items.append(NavItem(module_id=m.id, label=m.label, route=m.route))
    return [groups[k] for k in order]


def business_name(phone: str) -> str:
    """Tenant display name for the shell, with a safe fallback. Never raises —
    a module page is already owner-gated, and a transient lookup failure should
    still render the page rather than 500 it."""
    try:
        from backend.services.tenants_service import TenantsService

        tenant = TenantsService().get_tenant(phone)
        return getattr(tenant, "business_name", None) or "Beans&Co"
    except Exception:
        # Fail-open to the shell default so a lookup blip never 500s a gated page,
        # but log it so an outage is observable (org "log every issue" directive)
        # rather than silently rendering the wrong brand.
        logger.exception("business_name lookup failed for %s; using shell default", phone)
        return "Beans&Co"
