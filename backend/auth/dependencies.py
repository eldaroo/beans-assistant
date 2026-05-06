"""FastAPI dependencies for portal auth."""

import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status

from backend.services.auth_service import SESSION_COOKIE_NAME, AuthService


INTERNAL_TOKEN_HEADER = "x-internal-token"


def get_session_user(request: Request) -> Optional[dict]:
    """Decode the session cookie. Returns None if missing or invalid."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        service = AuthService()
    except RuntimeError:
        return None
    return service.verify_session(token)


def require_auth(request: Request) -> dict:
    """Reject unauthenticated requests with 401. Pending-onboarding sessions are
    NOT authenticated for the rest of the app — they only have access to the
    onboarding flow (see require_pending_session)."""
    user = get_session_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if user.get("kind") == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Onboarding pending. Complete it from /onboarding.",
        )
    request.state.user = user
    request.state.tenant_phone = user.get("phone_number")
    return user


def require_pending_session(request: Request) -> dict:
    """Only valid for the onboarding flow. Rejects active and missing sessions."""
    payload = get_session_user(request)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No onboarding session. Start over from /login.",
        )
    if payload.get("kind") != "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is for the onboarding flow only.",
        )
    if not payload.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pending session is malformed.",
        )
    request.state.pending = payload
    return payload


def require_role(*allowed_roles: str):
    """Reject if session role is not in allowed_roles."""
    def _checker(user: dict = Depends(require_auth)) -> dict:
        if user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return user
    return _checker


def _has_internal_token(request: Request) -> bool:
    expected = os.getenv("INTERNAL_SERVICE_TOKEN", "")
    if not expected:
        return False
    provided = request.headers.get(INTERNAL_TOKEN_HEADER, "")
    return bool(provided) and provided == expected


def require_tenant_match(request: Request, phone: str) -> dict:
    """For tenant-scoped routes: owner can only access own phone, admin bypasses, internal-token bypasses.

    Returns the session user dict, or a synthetic dict for internal-token requests.
    """
    if _has_internal_token(request):
        request.state.user = {"role": "service", "phone_number": phone}
        request.state.tenant_phone = phone
        return request.state.user

    user = get_session_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if user.get("kind") == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Onboarding pending. Complete it from /onboarding.",
        )
    if user.get("role") == "admin":
        request.state.user = user
        request.state.tenant_phone = phone
        return user
    if user.get("phone_number") != phone:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access denied",
        )
    request.state.user = user
    request.state.tenant_phone = phone
    return user


def require_internal_or_admin(request: Request) -> dict:
    """Bot endpoints: accept either INTERNAL_SERVICE_TOKEN header or admin session."""
    if _has_internal_token(request):
        request.state.user = {"role": "service"}
        return request.state.user
    user = get_session_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication or internal token required",
        )
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role or internal token required",
        )
    request.state.user = user
    return user
