"""The provider protocol every Control Center module meets.

A module is a server-side descriptor over the existing api/service/repository
triple, not a frontend component (plan.md architecture sketch). It exposes ONE
read-only provider:

  snapshot(phone) -> ModuleSnapshot    the module's tile headline + strip items,
                                        produced from a SINGLE tenant fetch.

A single provider (rather than separate ``headline`` + ``attention`` calls) is
deliberate: it makes "one bounded query per module" structurally enforceable
(plan.md risk 2). The shell calls ``snapshot`` once per module per render and
fans the result out into the tile and the strip. Adding a descriptor to
``registry.py`` makes a tile appear on the home and its items appear in the strip
with no edit to the home route or template (AC1).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Optional

# Headline.status values.
STATUS_OK = "ok"            # a live number from real data
STATUS_EMPTY = "empty"      # the module has no data yet (fresh tenant)
STATUS_DEGRADED = "degraded"  # the provider failed or timed out (set by the shell)


class Severity(IntEnum):
    """Attention severity. Lower value sorts first (most urgent on top, AC4).

    Each severity carries a shape cue so colour is never the only signal
    (mockup "shape-based severity cues"): triangle for HIGH, filled circle for
    MID, hollow ring for LOW. ``strip_class`` and ``shape`` map to the frozen
    mockup's ``.att.hi/.mid/.lo`` and ``.ic .tri/.cir/.ciro`` classes.
    """

    HIGH = 0
    MID = 1
    LOW = 2

    @property
    def strip_class(self) -> str:
        return {Severity.HIGH: "hi", Severity.MID: "mid", Severity.LOW: "lo"}[self]

    @property
    def shape(self) -> str:
        return {Severity.HIGH: "tri", Severity.MID: "cir", Severity.LOW: "ciro"}[self]


@dataclass(frozen=True)
class Headline:
    """A module's one number for its home tile.

    ``value`` is the already-formatted display string (e.g. ``"USD 3.1k"``);
    formatting lives with the module that owns the number, never in the shell.
    ``trend`` is an optional one-line caption under the number. ``trend_tone`` is
    ``good``/``warn``/``flat`` and selects the caption colour and the state dot;
    it is NOT a direction claim (no up/down arrow is rendered, because no module
    computes a period-over-period delta in M1). ``status`` is ``ok`` for a live
    number or ``empty`` for a module with no data yet; ``degraded`` is set by the
    shell when a provider fails (AC3), never by the module.
    """

    value: str
    trend: Optional[str] = None
    trend_tone: str = "flat"  # good | warn | flat
    status: str = STATUS_OK   # ok | empty | degraded


@dataclass(frozen=True)
class AttentionItem:
    """One item for the attention strip.

    ``text`` states what needs attention; ``action_label`` is the short verb on
    the right (e.g. "Reponer"); ``route`` is a drill-down suffix appended to the
    module's current surface (M1: a dashboard tab query such as ``?tab=stock``).
    ``module_id`` is stamped by the attention service during aggregation.
    """

    severity: Severity
    text: str
    action_label: str = "Ver"
    route: str = ""
    module_id: str = ""


@dataclass(frozen=True)
class ModuleSnapshot:
    """The result of one module fetch: the tile headline and the strip items."""

    headline: Headline
    attention: "list[AttentionItem]"


# The single provider callable. Takes the tenant phone, returns a snapshot. A
# provider may raise or run slow; the home service bounds it with a timeout and
# degrades the tile (AC3), never raising into the page.
SnapshotProvider = Callable[[str], ModuleSnapshot]


@dataclass(frozen=True)
class Module:
    """A registered Control Center module descriptor.

    ``route`` is the drill-down suffix appended to the module's current surface
    (M1: a dashboard tab, e.g. ``?tab=stock``). ``rail_group`` places the module
    in the left-rail nav sections ("" top group, "Operación", "Asistente").
    ``order`` fixes tile and rail ordering so the home is stable across requests.
    """

    id: str
    label: str
    route: str
    snapshot: SnapshotProvider
    rail_group: str = ""
    order: int = 100


@dataclass
class ModuleTile:
    """The rendered viewmodel for one home tile. Produced by the home service."""

    module_id: str
    label: str
    route: str
    value: str
    trend: Optional[str]
    trend_tone: str
    status: str
    rail_group: str = ""
