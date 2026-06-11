"""
Single source of truth for product variant vocabulary (colors and sizes).

This module is intentionally dependency-free (no DB, no LLM, no langchain) so
the expander, the SKU composer, and the resolver can all import the same
vocabulary without pulling in the rest of the pipeline. Spec T-001 / AC9:
the variant vocabulary is defined ONCE here and imported by both the expander
and the resolver. Do not re-declare color or size lists anywhere else.
"""
from __future__ import annotations

import unicodedata


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize_token(text: str) -> str:
    """Lowercase, accent-stripped form used for vocabulary lookup."""
    return _strip_accents(text or "").lower().strip()


# Surface form (accent-stripped, lowercase) -> canonical display color.
# Gender and number variants all collapse to one canonical color so SKUs and
# dedup keys are stable, while the expander keeps the owner's surface form for
# the product NAME so it reads naturally ("Medias Azules", not "Medias Azul").
COLOR_FORMS = {
    "azul": "Azul", "azules": "Azul",
    "gris": "Gris", "grises": "Gris",
    "negro": "Negro", "negra": "Negro", "negros": "Negro", "negras": "Negro",
    "blanco": "Blanco", "blanca": "Blanco", "blancos": "Blanco", "blancas": "Blanco",
    "rojo": "Rojo", "roja": "Rojo", "rojos": "Rojo", "rojas": "Rojo",
    "verde": "Verde", "verdes": "Verde",
    "amarillo": "Amarillo", "amarilla": "Amarillo", "amarillos": "Amarillo", "amarillas": "Amarillo",
    "rosa": "Rosa", "rosas": "Rosa", "rosado": "Rosado", "rosada": "Rosado",
    "celeste": "Celeste", "celestes": "Celeste",
    "violeta": "Violeta", "violetas": "Violeta",
    "naranja": "Naranja", "naranjas": "Naranja",
    "marron": "Marron", "marrones": "Marron",
    "dorado": "Dorado", "dorada": "Dorado", "dorados": "Dorado", "doradas": "Dorado",
    "plateado": "Plateado", "plateada": "Plateado",
    "fucsia": "Fucsia", "fucsias": "Fucsia",
    "lila": "Lila", "lilas": "Lila",
    "turquesa": "Turquesa", "turquesas": "Turquesa",
    "beige": "Beige", "beiges": "Beige",
    "multicolor": "Multicolor", "multicolores": "Multicolor",
}

# Letter sizes (talle). Surface form -> canonical display size.
SIZE_FORMS = {
    "xs": "XS",
    "s": "S",
    "m": "M",
    "l": "L",
    "xl": "XL",
    "xxl": "XXL",
    "xxxl": "XXXL",
}

# The keyword that introduces a size list ("talle s, m y l").
SIZE_KEYWORDS = {"talle", "talles", "size", "sizes"}


def is_color(token: str) -> bool:
    return normalize_token(token) in COLOR_FORMS


def is_size(token: str) -> bool:
    return normalize_token(token) in SIZE_FORMS


def canonical_color(token: str):
    return COLOR_FORMS.get(normalize_token(token))


def canonical_size(token: str):
    return SIZE_FORMS.get(normalize_token(token))


def is_discriminator(token: str) -> bool:
    """True when the token is a variant attribute (color or size) that must be
    retained in a SKU so siblings do not collide. Spec D-004 / T-007."""
    t = normalize_token(token)
    return t in COLOR_FORMS or t in SIZE_FORMS


# Resolver variant hints. Kept here so the resolver imports its variant
# vocabulary from the single source rather than re-declaring it. Spec T-001.
# Shape preserved from the resolver's prior in-module definition: a hinted
# canonical variant mapped to the accent-stripped stems that imply it.
VARIANT_HINT_TOKENS = {
    "dorada": ["dorad", "gold"],
    "negra": ["negr", "black"],
    "clasica": ["clasic"],
}
