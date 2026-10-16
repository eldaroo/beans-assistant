"""Home perf guard: the eighth concurrent snapshot fans out, it does not queue
(spec 004, perf guard / T-013 / AC10).

AC10: build_home for a live tenant still renders all tiles within the snapshot
deadline at production latency, with no new degraded tile from the eighth
concurrent snapshot; if the shared pool saturates, a note is filed against
eldaroo/beans-assistant#138 rather than inflating any snapshot or raising the
timeout.

The production-latency number itself is a live-cluster measurement (owner OAuth
session, observable via the build_home perf log line). What is provable here,
deterministically and without a DB, is the STRUCTURAL guarantee the AC rests on:

1. the pool has a worker slot for every registered module, so no module queues
   behind another (a ninth module without growing the pool is the documented
   saturation point tracked at #138);
2. the fan-out is concurrent — N snapshots that each take S seconds finish in
   ~S, not N*S — so the eighth snapshot adds no serial latency and no new
   degraded tile when every module returns within budget.
"""
import time

from backend.modules import home_service, registry
from backend.modules.protocol import Headline, Module, ModuleSnapshot, STATUS_OK


def test_pool_has_a_slot_per_registered_module():
    """No module queues: max_workers >= module count. This is the guard the AC
    names — a module beyond pool capacity would wait and burn the deadline, so
    growing the registry past the pool is the #138 saturation point."""
    module_count = len(registry.all_modules())
    assert home_service.POOL_MAX_WORKERS >= module_count, (
        f"pool ({home_service.POOL_MAX_WORKERS} workers) is smaller than the "
        f"registry ({module_count} modules): the extra module(s) would queue and "
        f"burn SNAPSHOT_TIMEOUT_S — grow the pool and resolve #138 first"
    )


def _slow_module(mid: str, delay_s: float) -> Module:
    def snapshot(phone: str):
        time.sleep(delay_s)
        return ModuleSnapshot(
            headline=Headline(value="ok", trend="", trend_tone="flat", status=STATUS_OK),
            attention=[],
        )

    return Module(id=mid, label=mid, route=f"/{mid}/{{phone}}",
                  snapshot=snapshot, rail_group="Operación", order=1)


def test_eight_snapshots_fan_out_and_none_degrade():
    """Eight modules that each sleep 0.3s complete well under 8*0.3s=2.4s (they
    run concurrently), and every tile renders real data (status != degraded)."""
    delay = 0.3
    n = 8
    mods = [_slow_module(f"m{i}", delay) for i in range(n)]

    start = time.monotonic()
    view = home_service.build_home("+100", modules=mods)
    elapsed = time.monotonic() - start

    # Concurrency: nowhere near the serial sum. Generous ceiling for CI noise.
    assert elapsed < delay * n * 0.6, (
        f"fan-out serialized: {elapsed:.2f}s for {n}x{delay}s (serial would be "
        f"{delay * n:.2f}s) — the eighth snapshot is queuing, not concurrent"
    )
    # No new degraded tile: all eight returned within the budget.
    assert len(view.tiles) == n
    assert all(t.status != "degraded" for t in view.tiles), (
        [t.module_id for t in view.tiles if t.status == "degraded"]
    )


def test_build_home_logs_the_perf_line(caplog):
    """The perf guard is observable: one build_home line carries elapsed_ms,
    the budget, pool size, and the degraded set, so saturation is visible in
    production logs (the #138 trigger) without a profiler."""
    import logging

    mods = [_slow_module("m0", 0.0)]
    with caplog.at_level(logging.INFO, logger="backend.modules.home_service"):
        home_service.build_home("+100", modules=mods)
    assert any("build_home" in r.message and "elapsed_ms" in r.message
               and "degraded=" in r.message for r in caplog.records)
