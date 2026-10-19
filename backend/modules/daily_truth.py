"""Hoy daily-truth headline (spec 006 T-010 / AC3).

One plain-Spanish sentence that tells the owner the truth of her day the moment
she lands on Hoy: how many sales she closed, how many are still waiting to be
paid, and the single thing that most needs her attention. It is deterministic
(A-Q17 default: computed from status data for v1, not phrased by an LLM), so it
costs nothing, never hallucinates, and is unit-testable.

The composition is a pure function (`daily_truth_headline`) over three plain
inputs — today's paid-sale count, today's unpaid-sale count, and the text of the
top attention item — so the wiring that gathers those (the home route) stays
separate from the sentence, and the sentence is tested in isolation (AC3).

HONESTY (Kaze law 4): the sentence never claims a number it was not given. When
there is nothing to say (no sales today, nothing in the attention strip) it says
exactly that — "Todavía no hay movimientos hoy." — rather than an empty string,
so Hoy always opens with a real sentence even for a fresh or quiet day.
"""
from __future__ import annotations

# The exact empty-day sentence named in AC3. Pinned as a constant so the route,
# the template and the test all speak the same string.
EMPTY_DAY = "Todavía no hay movimientos hoy."


def _ventas_clause(paid_today: int, unpaid_today: int) -> str | None:
    """The sales half of the sentence, or None when there were no sales today.

    ``paid_today`` and ``unpaid_today`` are counts of sales created today in the
    PAID and PENDING states. Spanish pluralization is explicit (no gettext in
    this codebase). Returns None when both counts are zero so the caller can fall
    back to the empty-day sentence or lead with the attention clause.
    """
    paid = max(0, int(paid_today or 0))
    unpaid = max(0, int(unpaid_today or 0))

    if paid == 0 and unpaid == 0:
        return None

    parts: list[str] = []
    if paid > 0:
        noun = "venta cobrada" if paid == 1 else "ventas cobradas"
        parts.append(f"{paid} {noun}")
    if unpaid > 0:
        noun = "pendiente de cobro" if unpaid == 1 else "pendientes de cobro"
        parts.append(f"{unpaid} {noun}")

    # "2 ventas cobradas" / "2 ventas cobradas y 1 pendiente de cobro".
    body = " y ".join(parts)
    return f"Hoy llevás {body}"


def daily_truth_headline(
    paid_today: int,
    unpaid_today: int,
    top_attention: str | None = None,
) -> str:
    """Compose the one-sentence Hoy daily-truth headline (AC3).

    Rules, in order:
      1. No sales today and nothing in the attention strip -> the empty-day
         sentence, so Hoy is never blank.
      2. No sales today but something needs attention -> lead with the attention
         item ("Lo más urgente hoy: ..."), since that is the only truth there is.
      3. Sales today -> state them, then append the top attention item as the
         second clause when there is one.

    ``top_attention`` is the already-rendered text of the most urgent attention
    item (``view.attention[0].text``), or None. The headline never re-ranks or
    re-formats it; it only decides whether and how to surface it.
    """
    attention = (top_attention or "").strip() or None
    ventas = _ventas_clause(paid_today, unpaid_today)

    if ventas is None:
        if attention is None:
            return EMPTY_DAY
        return f"Lo más urgente hoy: {attention}."

    if attention is None:
        return f"{ventas}."
    return f"{ventas}. Lo más urgente: {attention}."
