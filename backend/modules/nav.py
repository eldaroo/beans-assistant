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
import re
import unicodedata
from dataclasses import dataclass

from backend.modules import registry

logger = logging.getLogger(__name__)

# The synthetic Hoy overview tab (spec 006 AC1). Hoy is not a module ``group``;
# it is the overview surface that shows every tile plus the attention strip
# (AC6). It owns no modules, so it never appears as a module group and is added
# explicitly as the first tab.
HOY_ID = "hoy"


@dataclass(frozen=True)
class NavItem:
    module_id: str
    label: str
    route: str


@dataclass(frozen=True)
class NavGroup:
    label: str
    items: list


@dataclass(frozen=True)
class OwnerTab:
    """One owner-facing job tab in the simplified Command Center (spec 006).

    ``id`` is the stable slug the shell keys panels and the active-tab highlight
    off (``hoy``, ``operacion``, ``costos``). ``label`` is the owner-facing tab
    name. ``items`` are the modules that live under this tab, in registry order
    (empty for Hoy, which is the overview). ``count`` is ``len(items)``.
    """

    id: str
    label: str
    items: list  # list[NavItem]

    @property
    def count(self) -> int:
        return len(self.items)


def _tab_slug(label: str) -> str:
    """Stable slug id for a tab label. Known labels use the mockup's ids via
    ``registry.TAB_IDS``; an unknown group label (a tab added later by setting a
    new ``group`` on a module) derives an accent-stripped, lowercased slug from
    the WHOLE label so it still renders without a template edit (AC1). The slug is
    whitelisted to ``[a-z0-9-]`` (so a label can never carry metacharacters into a
    DOM id or a querySelector) and never equals the reserved Hoy overview id."""
    known = registry.TAB_IDS.get(label)
    if known:
        return known
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_label.lower()).strip("-")
    if not slug or slug == HOY_ID:
        slug = f"{slug}-tab" if slug else "tab"
    return slug


def owner_tabs() -> "list[OwnerTab]":
    """The three owner-facing job tabs, derived from the module registry (AC1).

    Hoy (overview, no owned modules) is always first. Each distinct module
    ``group`` becomes a tab, in the order the groups first appear in the registry
    (so the layout is stable). Every registered module lands under exactly one
    tab via its ``group`` (falling back to the default Operación tab when unset),
    so the module-group tabs together cover all eight modules. Adding a module
    with a new ``group`` value adds its tab here with no template edit; the shell
    renders whatever ``owner_tabs()`` returns.
    """
    by_group: dict[str, list[NavItem]] = {}
    group_order: list[str] = []
    for m in sorted(registry.all_modules(), key=lambda mod: mod.order):
        group = m.group or registry.TAB_OPERACION
        if group not in by_group:
            by_group[group] = []
            group_order.append(group)
        by_group[group].append(NavItem(module_id=m.id, label=m.label, route=m.route))

    # Hoy first, then module groups in their registry-preferred order (TAB_ORDER)
    # with any extra groups appended in first-appearance order.
    ordered_groups: list[str] = []
    for g in registry.TAB_ORDER:
        if g in by_group and g not in ordered_groups:
            ordered_groups.append(g)
    for g in group_order:
        if g not in ordered_groups:
            ordered_groups.append(g)

    tabs = [OwnerTab(id=HOY_ID, label=registry.TAB_HOY, items=[])]
    used = {HOY_ID}
    for g in ordered_groups:
        sid = _tab_slug(g)
        if sid in used:  # two distinct group labels that slug to the same id
            n = 2
            while f"{sid}-{n}" in used:
                n += 1
            sid = f"{sid}-{n}"
        used.add(sid)
        tabs.append(OwnerTab(id=sid, label=g, items=by_group[g]))
    return tabs


def tab_id_for_module(module_id: str) -> str:
    """The owner tab id a module page sits under, for the shell's active-tab
    highlight (spec 006 T-005). Resolved via ``owner_tabs()`` (not a bare
    ``_tab_slug``) so it stays consistent with any de-duplication owner_tabs
    applied. Falls back to Hoy for an unknown module id so a page never renders
    with no tab selected."""
    for tab in owner_tabs():
        if any(item.module_id == module_id for item in tab.items):
            return tab.id
    return HOY_ID


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
