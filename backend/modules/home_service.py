"""Home service: build the status-home viewmodel from the registry.

Iterates the module registry, asks each module for its single ``snapshot``, and
turns the snapshots into tiles + the attention strip. Every snapshot call is run
in a worker thread with a per-module timeout, so one slow OR broken module
renders a degraded tile and never raises into the page or blocks the others
(AC3, risk 2). The route runs ``build_home`` off the event loop (asyncio.to_thread)
so the whole page build never blocks the worker. The service owns no domain
logic; it only turns the provider protocol into a viewmodel.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field

from backend.modules import attention_service, registry
from backend.modules.protocol import STATUS_DEGRADED, STATUS_EMPTY, Module, ModuleSnapshot, ModuleTile

logger = logging.getLogger(__name__)

# Shared snapshot deadline. All module snapshots run concurrently on one pool;
# a module that has not returned by the deadline degrades to a tile rather than
# stalling the page (risk 2, the "slow" half of fail-open). The deadline bounds
# how long build_home WAITS; a genuinely hung worker is left orphaned on the
# pool (a thread cannot be killed in Python), so a DB statement_timeout should
# back this so the worker itself eventually unblocks the pool slot.
#
# Budget note (2026-10-14): in production each provider opens its own tenant
# scope, and tenant_context resolves the tenant and binds the schema over a
# fresh cross-container DB connection. The DB work itself is ~0.8s, but that
# per-call connection-plus-resolve overhead puts a single provider at ~3.3s and
# the slowest of seven concurrent snapshots at ~6s on the live cluster. A 3.0s
# budget degraded EVERY tile on the real home even though every provider
# returns correct data. The budget is raised to 10.0s (the value verified green
# against the live home: all seven tiles rendered real numbers, ~6s wall-clock)
# so the home shows its real figures with headroom over the observed tail. This
# is a single-user mitigation: the tail drifts up under concurrent loads because
# _POOL is a shared pool and queue-wait burns the budget, so the durable fix is
# connection pooling / cached tenant resolution AND pool sizing so a snapshot
# costs ~0.3s again (tracked: eldaroo/beans-assistant#138), after which this
# budget comes back down under 3.0s.
SNAPSHOT_TIMEOUT_S = 10.0

# One shared pool, fanned out across modules so total latency is the slowest
# module, not the sum. As of spec 004 Cohort B the registry holds EIGHT modules
# (caja, productos, stock, ventas, costos, produccion, logistica, proveedores)
# against max_workers=8 — the pool is at exact capacity, zero headroom. A ninth
# module would queue behind the others and its result-wait would start burning
# the SNAPSHOT_TIMEOUT_S budget, so grow this pool (and resolve the connection-
# reuse debt eldaroo/beans-assistant#138) before registering a 9th module.
# One worker slot per registered module (the registry holds 8 as of cohort B),
# so no module queues behind another and total latency is the slowest module,
# not the sum. A ninth module would queue and burn SNAPSHOT_TIMEOUT_S, so grow
# this AND resolve the connection-reuse debt (#138) before registering a 9th.
POOL_MAX_WORKERS = 8
_POOL = ThreadPoolExecutor(max_workers=POOL_MAX_WORKERS, thread_name_prefix="cc-snapshot")


@dataclass
class RailGroup:
    label: str
    items: list = field(default_factory=list)  # list[ModuleTile]


@dataclass
class HomeView:
    tiles: list  # list[ModuleTile], registry order
    attention: list  # list[AttentionItem], prioritized + capped
    rail_groups: list  # list[RailGroup], nav derived from the registry

    @property
    def is_empty(self) -> bool:
        """True only for a fresh tenant: every tile reports no data AND none
        failed. An all-degraded home (e.g. the DB is down) is NOT empty — it
        renders its degraded tiles so the outage is visible, never the
        "load your data" welcome (which would be a false claim)."""
        return bool(self.tiles) and all(t.status == STATUS_EMPTY for t in self.tiles)


def _tile_from(module: Module, snap: ModuleSnapshot | None) -> ModuleTile:
    if snap is None:
        return ModuleTile(
            module_id=module.id,
            label=module.label,
            route=module.route,
            value="—",
            trend="no disponible",
            trend_tone="warn",
            status=STATUS_DEGRADED,
            rail_group=module.rail_group,
        )
    h = snap.headline
    return ModuleTile(
        module_id=module.id,
        label=module.label,
        route=module.route,
        value=h.value,
        trend=h.trend,
        trend_tone=h.trend_tone,
        status=h.status,
        rail_group=module.rail_group,
    )


def _rail_groups(tiles: "list[ModuleTile]") -> "list[RailGroup]":
    groups: dict[str, RailGroup] = {}
    order: list[str] = []
    for t in tiles:
        key = t.rail_group or ""
        if key not in groups:
            groups[key] = RailGroup(label=key, items=[])
            order.append(key)
    for t in tiles:
        groups[t.rail_group or ""].items.append(t)
    return [groups[k] for k in order]


def build_home(phone: str, modules: "list[Module] | None" = None) -> HomeView:
    """Compose the status-home viewmodel for a tenant. One snapshot per module,
    all fanned out concurrently on the shared pool under one deadline.

    A module that has not returned by the deadline (slow) or that raises
    (broken) degrades to a tile and never blocks the others. A genuinely hung
    worker is left running on the pool (orphaned) rather than waited on, so
    build_home returns by the deadline regardless. Each provider opens its own
    tenant scope inside its worker thread, so the tenant contextvar binds in the
    thread that queries."""
    mods = list(modules) if modules is not None else registry.all_modules()
    mods = sorted(mods, key=lambda m: m.order)

    started = time.monotonic()
    futures = [(m, _POOL.submit(m.snapshot, phone)) for m in mods]
    deadline = started + SNAPSHOT_TIMEOUT_S
    snaps: "list[tuple[Module, ModuleSnapshot | None]]" = []
    for m, fut in futures:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            snaps.append((m, fut.result(timeout=remaining)))
        except FuturesTimeout:
            logger.warning("snapshot timed out for module %s (>%.1fs)", m.id, SNAPSHOT_TIMEOUT_S)
            snaps.append((m, None))
        except Exception:
            logger.exception("snapshot failed for module %s", m.id)
            snaps.append((m, None))

    # Perf guard (spec 004 AC10 / T-013): one observable line per home build so
    # the eighth-concurrent-snapshot budget is measurable at production latency
    # without a profiler. `degraded` names the modules that timed out or raised;
    # a non-empty set on a healthy tenant is the pool-saturation signal the AC
    # says to file against eldaroo/beans-assistant#138 — never silenced by
    # inflating a snapshot or raising SNAPSHOT_TIMEOUT_S.
    elapsed_ms = (time.monotonic() - started) * 1000.0
    degraded = [m.id for m, snap in snaps if snap is None]
    logger.info(
        "build_home modules=%d elapsed_ms=%.0f budget_ms=%.0f pool_workers=%d degraded=%s",
        len(mods), elapsed_ms, SNAPSHOT_TIMEOUT_S * 1000.0, POOL_MAX_WORKERS, degraded or "none",
    )

    tiles = [_tile_from(m, snap) for m, snap in snaps]
    attention = attention_service.aggregate(
        [(m.id, snap.attention if snap else []) for m, snap in snaps]
    )
    return HomeView(tiles=tiles, attention=attention, rail_groups=_rail_groups(tiles))
