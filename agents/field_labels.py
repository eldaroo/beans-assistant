"""
Single source of truth for user-facing field labels and the missing-field
message.

Before this module, write_agent.py and graph.py each carried their own copy of
a technical-name -> friendly-Spanish table. The two drifted and both fell back
to the literal string "ese dato", which is exactly what produced the screenshot
failure ("Me faltan algunos datos: ese dato, ese dato") when the resolver handed
up an indexed key like ``items[0].name`` that neither table could translate.

Per ARCHITECTURE.md D-006 the tables collapse here, and the renderer understands
two shapes:

- a flat scalar field name (single-product and non-product paths), translated
  through ``FIELD_LABELS`` with a generic fallback, and
- a structured per-item miss ``{"product": "<name>", "field": "<field>"}`` (the
  multi-product path), rendered as "<Producto>: falta <campo>" so a per-item
  miss never degrades to "ese dato" (spec AC4 / T-015).

Dependency-free at import (no DB, no langchain) so both the resolver and the
graph nodes can import it without pulling in the rest of the pipeline.
"""
from __future__ import annotations

from typing import Any, Dict, List, Union

# Technical field name -> friendly Argentine-Spanish label. One table, imported
# by write_agent.py and graph.py. Do not re-declare a translation table anywhere
# else (spec D-006 / AC9 single-source discipline).
FIELD_LABELS: Dict[str, str] = {
    "unit_price": "el precio de venta",
    "unit_price_cents": "el precio de venta",
    "unit_cost": "el costo de producción",
    "unit_cost_cents": "el costo de producción",
    "name": "el nombre del producto",
    "amount": "el monto",
    "amount_cents": "el monto",
    "description": "la descripción",
    "product_ref": "el producto",
    "product_id": "el producto",
    "quantity": "la cantidad",
    "items": "los productos",
    "sku": "el código del producto",
}

# Generic label so a column name we forgot to translate never leaks to the user
# on a flat scalar miss. Item misses never reach this fallback because they
# carry the product name and a known field (see render_missing_entry).
GENERIC_LABEL = "ese dato"

# Sentinel markers that are not real fields and must not be translated or shown
# as a field label. They route to dedicated copy elsewhere.
SENTINELS = {"ambiguous_comma_name_split"}


def label_for(field: str) -> str:
    """Friendly label for a flat scalar field name, generic fallback otherwise."""
    return FIELD_LABELS.get(field, GENERIC_LABEL)


def is_item_miss(entry: Any) -> bool:
    """True when the entry is a structured per-item miss {product, field}."""
    return isinstance(entry, dict) and "field" in entry


def render_item_miss(entry: Dict[str, Any]) -> str:
    """Render a structured per-item miss as "<Producto>: falta <campo>"."""
    product = entry.get("product") or "Ese producto"
    label = label_for(entry.get("field", ""))
    return f"{product}: falta {label}"


def compose_missing_message(missing: List[Union[str, Dict[str, Any]]]) -> str:
    """Compose the user-facing missing-fields message from a mixed list.

    Accepts a list whose members are either flat field-name strings
    (single-product / non-product paths) or structured {product, field} dicts
    (the multi-product path). Sentinels are dropped here; their copy is owned by
    the caller. Returns the full message, voseo, no emoji, no exclamation.
    """
    item_lines: List[str] = []
    scalar_labels: List[str] = []

    for entry in missing:
        if is_item_miss(entry):
            item_lines.append(render_item_miss(entry))
        elif isinstance(entry, str) and entry in SENTINELS:
            continue
        else:
            scalar_labels.append(label_for(str(entry)))

    # Per-item misses lead (they are the most actionable: they name a product).
    if item_lines and not scalar_labels:
        if len(item_lines) == 1:
            return f"{item_lines[0]}. ¿Me lo decís?"
        body = "\n• ".join(item_lines)
        return f"Me faltan datos de algunos productos:\n• {body}\n\n¿Me los decís?"

    if scalar_labels and not item_lines:
        if len(scalar_labels) == 1:
            return f"Me falta un dato: *{scalar_labels[0]}*\n\n¿Me lo podés decir?"
        body = "\n• ".join(scalar_labels)
        return f"Me faltan algunos datos:\n• {body}\n\n¿Me los podés decir?"

    # Mixed: item misses first, then the scalar gaps.
    lines = list(item_lines) + list(scalar_labels)
    body = "\n• ".join(lines)
    return f"Me faltan algunos datos:\n• {body}\n\n¿Me los podés decir?"
