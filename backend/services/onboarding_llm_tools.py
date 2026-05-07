"""Tool surface for the LLM-driven onboarding flow (ADR-002, M3.2 + M3.3).

This module is the single source of truth for what Gemini sees when it
decides to capture a field during onboarding. It exposes:

- Six Pydantic argument models (one per tool). The model docstrings ARE
  the tool descriptions when bound via LangChain's ``bind_tools``.
- Three result models (``ToolOk``, ``ToolConflict``, ``ToolHardFail``)
  with a discriminated-union alias ``ToolResult``.
- Six executors wired to real persistence in M3.3.
- A ``TOOL_REGISTRY`` mapping from tool name to ``(args_model, executor)``
  that the dispatcher in ``onboarding_web`` iterates over.

Failure-mode policy (ADR-002, "Failure-mode recovery"):
- ``phone_in_use``       : phone collides with an existing tenant.
- ``phone_in_pending``   : phone collides with another live pending session.
- ``validation_error``   : the LLM sent malformed args (Pydantic catches
                           most of these before the executor runs).
- ``db_error``           : transactional write failed.
- ``session_expired``    : pending row vanished mid-conversation.
- ``rate_limited``       : upstream API limit hit.
"""

import json
import re
from datetime import datetime
from typing import Any, Literal, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Tool argument models. Docstrings are the LLM-facing tool descriptions.
# Keep them voseo-neutral, sentence case, no em-dashes, no emojis.
# ---------------------------------------------------------------------------


class CaptureBusinessNameArgs(BaseModel):
    """Anota el nombre del negocio."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Nombre comercial del negocio.",
    )


class CapturePhoneArgs(BaseModel):
    """Anota el WhatsApp del negocio."""

    phone: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Numero de WhatsApp en formato internacional, empezando con '+'.",
    )


class CaptureCurrencyArgs(BaseModel):
    """Anota la moneda del negocio."""

    currency: Literal["USD", "ARS", "EUR", "AUD"] = Field(
        ...,
        description="Codigo de moneda ISO.",
    )


class CaptureLanguageArgs(BaseModel):
    """Anota el idioma del usuario."""

    language: Literal["es", "en"] = Field(
        ...,
        description="Codigo de idioma ISO.",
    )


class CaptureOwnerNameArgs(BaseModel):
    """Anota el nombre del dueno del negocio. Opcional; si no se da, el sistema usa el nombre de la cuenta de Google."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Nombre del dueno.",
    )


class ConfirmAndCreateTenantArgs(BaseModel):
    """Termina onboarding. Crea el tenant en la base de datos. Llamar solo cuando se tienen nombre, WhatsApp, moneda e idioma."""

    # Intentionally no fields. The executor reads the captured state from
    # the pending session row by ``session_email``.
    pass


# ---------------------------------------------------------------------------
# Tool result models.
# ---------------------------------------------------------------------------


class ToolOk(BaseModel):
    """Tool executed successfully and merged data into state."""

    ok: Literal[True] = True
    captured: dict[str, Any] = Field(
        ...,
        description="The field(s) just written, one entry per tool.",
    )
    label_es: str = Field(
        ...,
        description="Verb-led card label, e.g. 'Anoté el nombre del negocio: Cafe Catuai'.",
    )


class ToolConflict(BaseModel):
    """Soft failure. The LLM should retry by asking the user differently."""

    ok: Literal[False] = False
    error: Literal["phone_in_use", "phone_in_pending", "validation_error"]
    message_es: str = Field(
        ...,
        description="Plain-Spanish description of the conflict, for the LLM to paraphrase.",
    )


class ToolHardFail(BaseModel):
    """Infra-level failure. The LLM apologizes once and the user retries."""

    ok: Literal[False] = False
    error: Literal["db_error", "session_expired", "rate_limited"]
    message_es: str = Field(
        ...,
        description="Plain-Spanish description of the failure, for the LLM to paraphrase.",
    )


# Discriminated union for the dispatcher's type hints.
ToolResult = Union[ToolOk, ToolConflict, ToolHardFail]


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _get_repo():
    """Lazy-import the repo so the module stays importable without psycopg2."""
    from backend.repositories.pending_onboarding_repository import (
        PendingOnboardingRepository,
    )

    return PendingOnboardingRepository()


def _phone_is_valid(phone: str) -> bool:
    """Phone must start with '+' and contain only digits after the prefix.

    Length 8-20 chars total (per the M3.3 contract). The Pydantic model
    already enforces 1..20; we tighten the lower bound and the format
    here so the executor returns a soft ToolConflict instead of letting
    a malformed value reach the DB.
    """
    if not phone or not phone.startswith("+"):
        return False
    rest = phone[1:]
    if len(phone) < 8 or len(phone) > 20:
        return False
    return rest.isdigit() and len(rest) >= 7


def _phone_in_tenants(phone: str) -> bool:
    """Direct SELECT against public.tenants for unique-phone collision."""
    repo = _get_repo()
    conn = repo._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.tenants WHERE phone_number = %s LIMIT 1",
                (phone,),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def _phone_to_schema_name(phone: str) -> str:
    """Mirror tenant_manager.phone_to_schema_name without importing it
    (keeps this module DB-only). Sanitize to alphanumerics + underscore.
    """
    sanitized = re.sub(r"[^0-9A-Za-z]+", "_", phone.lstrip("+")).strip("_")
    if not sanitized:
        sanitized = "default"
    return f"tenant_{sanitized}"


# ---------------------------------------------------------------------------
# Executors.
# ---------------------------------------------------------------------------


def _capture_field(session_email: str, field: str, value: Any, label_es: str) -> ToolResult:
    """Shared body for the four simple capture executors."""
    try:
        _get_repo().merge_state(session_email, {field: value})
    except LookupError:
        return ToolHardFail(
            error="session_expired",
            message_es="La sesión venció. Iniciá sesión de nuevo.",
        )
    except Exception:
        return ToolHardFail(
            error="db_error",
            message_es="Algo se rompió. Probá en un minuto.",
        )
    return ToolOk(captured={field: value}, label_es=label_es)


def execute_capture_business_name(
    session_email: str, args: CaptureBusinessNameArgs
) -> ToolResult:
    """Persist the business name into the pending session state."""
    return _capture_field(
        session_email,
        "business_name",
        args.name,
        f"Anoté el nombre del negocio: {args.name}",
    )


def execute_capture_phone(
    session_email: str, args: CapturePhoneArgs
) -> ToolResult:
    """Persist the WhatsApp phone into the pending session state.

    Three checks before writing:
      1. format (`+` prefix, 8..20 chars total, digits-only suffix).
      2. tenants collision (someone already owns this number).
      3. pending collision (another live pending session has it).
    """
    phone = args.phone.strip()
    if not _phone_is_valid(phone):
        return ToolConflict(
            error="validation_error",
            message_es="Necesito el WhatsApp en formato internacional, empezando con +.",
        )

    try:
        if _phone_in_tenants(phone):
            return ToolConflict(
                error="phone_in_use",
                message_es="Ese WhatsApp ya tiene un negocio registrado en Bitácora AI. Decime otro.",
            )

        repo = _get_repo()
        if repo.phone_in_use_by_other_pending(phone, session_email):
            return ToolConflict(
                error="phone_in_pending",
                message_es="Otro usuario está configurando ese mismo WhatsApp ahora mismo. Decime otro.",
            )

        try:
            repo.merge_state(session_email, {"phone": phone})
        except LookupError:
            return ToolHardFail(
                error="session_expired",
                message_es="La sesión venció. Iniciá sesión de nuevo.",
            )
    except Exception:
        return ToolHardFail(
            error="db_error",
            message_es="Algo se rompió. Probá en un minuto.",
        )

    return ToolOk(
        captured={"phone": phone},
        label_es=f"Anoté el WhatsApp del negocio: {phone}",
    )


def execute_capture_currency(
    session_email: str, args: CaptureCurrencyArgs
) -> ToolResult:
    """Persist the currency into the pending session state."""
    return _capture_field(
        session_email,
        "currency",
        args.currency,
        f"Anoté la moneda del negocio: {args.currency}",
    )


def execute_capture_language(
    session_email: str, args: CaptureLanguageArgs
) -> ToolResult:
    """Persist the language into the pending session state."""
    return _capture_field(
        session_email,
        "language",
        args.language,
        f"Anoté el idioma del usuario: {args.language}",
    )


def execute_capture_owner_name(
    session_email: str, args: CaptureOwnerNameArgs
) -> ToolResult:
    """Persist the owner name into the pending session state."""
    return _capture_field(
        session_email,
        "owner_name",
        args.name,
        f"Anoté el nombre del dueño: {args.name}",
    )


def execute_confirm_and_create_tenant(
    session_email: str, args: ConfirmAndCreateTenantArgs
) -> ToolResult:
    """Atomically create the tenant + tenant schema + app_user, delete the
    pending session, all inside one Postgres transaction.

    Rollback on any failure. ``IntegrityError`` against
    ``public.tenants.phone_number`` is surfaced as ``phone_in_use``;
    every other exception is ``db_error``.
    """
    repo = _get_repo()

    try:
        session_row = repo.get(session_email)
    except Exception:
        return ToolHardFail(
            error="db_error",
            message_es="Algo se rompió. Probá en un minuto.",
        )

    if session_row is None:
        return ToolHardFail(
            error="session_expired",
            message_es="La sesión venció. Iniciá sesión de nuevo.",
        )

    state = session_row.get("state") or {}
    business_name = state.get("business_name")
    phone = state.get("phone")
    currency = state.get("currency")
    language = state.get("language")
    # owner_name is optional; fall back to the Google name embedded in the
    # pending JWT, surfaced via state by the dispatcher when the LLM doesn't
    # call capture_owner_name. The dispatcher pre-seeds it; we only check.
    owner_name = state.get("owner_name") or ""

    missing = [
        ("nombre del negocio", business_name),
        ("WhatsApp", phone),
        ("moneda", currency),
        ("idioma", language),
    ]
    for label, value in missing:
        if not value:
            return ToolConflict(
                error="validation_error",
                message_es=f"Me falta {label} antes de poder crear el negocio.",
            )

    # One transaction: tenants + tenant schema + app_users + delete pending.
    try:
        import psycopg2
    except Exception:
        return ToolHardFail(
            error="db_error",
            message_es="Algo se rompió. Probá en un minuto.",
        )

    schema_name = _phone_to_schema_name(phone)

    # Provision the per-tenant schema WITH its tables BEFORE the main
    # transaction. The previous version only ran `CREATE SCHEMA IF NOT
    # EXISTS` here — leaving the schema empty. With search_path set to
    # `tenant_X, public` on every read, queries against tables that
    # didn't exist in tenant_X silently fell back to `public.products`
    # / `public.sales`, leaking data from earlier tests across every new
    # tenant's dashboard. Calling create_tenant_schema (idempotent: uses
    # IF NOT EXISTS for every DDL) fixes the leak by giving the new
    # tenant its own empty tables to land on first.
    try:
        from database_pg import create_tenant_schema as _create_schema
        _create_schema(schema_name)
    except Exception:
        return ToolHardFail(
            error="db_error",
            message_es="Algo se rompió al preparar tu negocio. Probá en un minuto.",
        )

    conn = repo._connect()
    try:
        try:
            with conn.cursor() as cur:
                config = {
                    "currency": currency,
                    "language": language,
                    "owner_name": owner_name,
                    "business_name": business_name,
                    "phone_number": phone,
                }
                created_at = datetime.utcnow().isoformat()
                config["created_at"] = created_at

                cur.execute(
                    """
                    INSERT INTO public.tenants
                        (phone_number, business_name, created_at, status, config)
                    VALUES
                        (%s, %s, %s, 'active', %s::jsonb)
                    """,
                    (phone, business_name, created_at, json.dumps(config)),
                )

                cur.execute(
                    """
                    INSERT INTO public.app_users (google_email, phone_number, role)
                    VALUES (%s, %s, 'owner')
                    """,
                    ((session_email or "").strip().lower(), phone),
                )

                # Delete the pending row inside the same transaction. The
                # M3.1 repo supports the external-conn contract.
                repo.delete(session_email, conn=conn)

            conn.commit()
        except psycopg2.IntegrityError as e:
            conn.rollback()
            # Heuristic: any IntegrityError on the tenants insert means
            # the phone got grabbed in the race.
            msg = str(e).lower()
            if "phone_number" in msg or "tenants" in msg:
                return ToolConflict(
                    error="phone_in_use",
                    message_es="Ese WhatsApp ya tiene un negocio registrado en Bitácora AI. Decime otro.",
                )
            return ToolHardFail(
                error="db_error",
                message_es="Algo se rompió. Probá en un minuto.",
            )
        except Exception:
            conn.rollback()
            return ToolHardFail(
                error="db_error",
                message_es="Algo se rompió. Probá en un minuto.",
            )
    finally:
        conn.close()

    return ToolOk(
        captured={
            "tenant_created": True,
            "redirect_to": f"/tenants/{phone}",
        },
        label_es="Listo, creé tu negocio en Bitácora AI.",
    )


# ---------------------------------------------------------------------------
# Registry. The dispatcher iterates over this when it routes the LLM's
# tool calls to the matching executor.
# ---------------------------------------------------------------------------


TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Any]] = {
    "capture_business_name":     (CaptureBusinessNameArgs,    execute_capture_business_name),
    "capture_phone":             (CapturePhoneArgs,           execute_capture_phone),
    "capture_currency":          (CaptureCurrencyArgs,        execute_capture_currency),
    "capture_language":          (CaptureLanguageArgs,        execute_capture_language),
    "capture_owner_name":        (CaptureOwnerNameArgs,       execute_capture_owner_name),
    "confirm_and_create_tenant": (ConfirmAndCreateTenantArgs, execute_confirm_and_create_tenant),
}
