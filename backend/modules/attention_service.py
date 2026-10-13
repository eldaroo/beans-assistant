"""Attention service: aggregate across the registry, sort by severity, cap.

The strip is the CEO's single "what needs me today" list. The service takes the
attention items already produced by each module's single ``snapshot`` fetch
(the home service owns that fetch, so the strip adds no extra query), stamps
them with the module id, sorts most-urgent first, and caps the strip so it stays
a short list and not a second to-do pile (AC4, risk 3).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Tuple

from backend.modules.protocol import AttentionItem

# Cap on strip length. A short, ordered strip; overflow is reachable from the
# modules themselves. OQ4: thresholds (and this cap) surface as settings later.
ATTENTION_CAP = 5


def prioritize(items: "list[AttentionItem]", cap: int = ATTENTION_CAP) -> "list[AttentionItem]":
    """Sort items most-urgent first (stable within a severity) and cap."""
    ordered = sorted(items, key=lambda i: int(i.severity))
    return ordered[:cap]


def aggregate(
    module_items: "Iterable[Tuple[str, list[AttentionItem]]]",
    cap: int = ATTENTION_CAP,
) -> "list[AttentionItem]":
    """Flatten per-module attention items, stamp the module id, sort, and cap.

    ``module_items`` is an iterable of ``(module_id, items)`` pairs. A module
    that failed its snapshot contributes an empty list (the home service drops
    it), so aggregation is inherently fail-open.
    """
    collected: list[AttentionItem] = []
    for module_id, items in module_items:
        for item in items or []:
            collected.append(replace(item, module_id=module_id))
    return prioritize(collected, cap=cap)
