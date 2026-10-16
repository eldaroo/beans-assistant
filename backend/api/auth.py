"""Google OAuth login routes for the customer portal."""

import logging
import os
from pathlib import Path

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.services.auth_service import (
    SESSION_COOKIE_NAME,
    AuthService,
    UserNotAuthorizedError,
)

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

oauth = OAuth()
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={"scope": "openid email profile"},
)


def _cookie_kwargs() -> dict:
    secure = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    domain = os.getenv("COOKIE_DOMAIN") or None
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "domain": domain,
        "path": "/",
    }


@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GOOGLE_REDIRECT_URI not configured",
        )
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        logger.warning(f"google_callback: oauth error: {exc}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Login failed. Try again."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").strip().lower()
    if not email or not userinfo.get("email_verified", False):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Google did not return a verified email."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    auth = AuthService()
    try:
        user = auth.authorize_google_email(email)
    except UserNotAuthorizedError:
        # Invite-only: an unauthorized email is sent back to the login with a
        # clear message, not into an onboarding flow (retired with the
        # single-business pivot).
        logger.info(f"google_callback: unauthorized email {email}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Tu cuenta no está autorizada. Escribinos para pedir acceso."},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    session_token = auth.issue_session(user)
    # One surface: everyone lands on the Control Center home (phone-less; the
    # single-business middleware resolves the tenant from the session).
    response = RedirectResponse(url="/home", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=auth.ttl_seconds,
        **_cookie_kwargs(),
    )
    return response


@router.post("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        domain=_cookie_kwargs().get("domain"),
        path="/",
    )
    return response
