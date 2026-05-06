"""Auth service: session signing and authorization checks."""

import os
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from backend.repositories.app_users_repository import AppUsersRepository


SESSION_COOKIE_NAME = "beansco_session"
DEFAULT_TTL_SECONDS = 8 * 60 * 60          # 8h, active session
PENDING_TTL_SECONDS = 30 * 60              # 30 min, onboarding window


class AuthError(Exception):
    """Base auth error."""


class UserNotAuthorizedError(AuthError):
    """Email is not in app_users (no portal access granted)."""


class AuthService:
    def __init__(self, repo: Optional[AppUsersRepository] = None):
        self.repo = repo or AppUsersRepository()
        self._secret = os.getenv("SESSION_SECRET")
        if not self._secret:
            raise RuntimeError("SESSION_SECRET env var must be set")
        self._serializer = URLSafeTimedSerializer(self._secret, salt="beansco-session")

    @property
    def ttl_seconds(self) -> int:
        try:
            return int(os.getenv("SESSION_TTL_HOURS", "8")) * 3600
        except ValueError:
            return DEFAULT_TTL_SECONDS

    @property
    def pending_ttl_seconds(self) -> int:
        return PENDING_TTL_SECONDS

    def authorize_google_email(self, email: str) -> dict:
        """Look up email in app_users. Raise if not authorized. Update last_login on success."""
        user = self.repo.get_by_email(email)
        if not user:
            raise UserNotAuthorizedError(email)
        self.repo.update_last_login(user["id"])
        return user

    def issue_session(self, user: dict) -> str:
        """Active session: user owns a tenant and is fully provisioned."""
        payload = {
            "kind": "active",
            "user_id": user["id"],
            "email": user["google_email"],
            "phone_number": user["phone_number"],
            "role": user["role"],
        }
        return self._serializer.dumps(payload)

    def issue_pending_session(self, email: str, name: Optional[str] = None, picture: Optional[str] = None) -> str:
        """Pending session: Google verified the email but it has no tenant yet.
        Grants access to the onboarding flow only. Does NOT grant access to /admin
        or /tenants/{phone}.
        """
        payload = {
            "kind": "pending",
            "email": (email or "").strip().lower(),
            "name": name or "",
            "picture": picture or "",
        }
        return self._serializer.dumps(payload)

    def verify_session(self, token: str) -> Optional[dict]:
        """Decode any session token. The TTL applied depends on the kind."""
        if not token:
            return None
        # Try the active TTL first (the common case).
        try:
            payload = self._serializer.loads(token, max_age=self.ttl_seconds)
        except SignatureExpired:
            # Token's age exceeds the active TTL. It might still be a fresh
            # pending session (which has a shorter TTL) — the loader is the
            # same; the `kind` field tells us. Re-decode without max_age and
            # then enforce the pending TTL ourselves.
            try:
                payload = self._serializer.loads(token, max_age=self.ttl_seconds * 8)
            except (SignatureExpired, BadSignature):
                return None
        except BadSignature:
            return None

        # Default kind for tokens issued before the pending-session feature.
        if "kind" not in payload:
            payload["kind"] = "active"

        # Enforce the kind-specific TTL on pending tokens.
        if payload["kind"] == "pending":
            try:
                self._serializer.loads(token, max_age=self.pending_ttl_seconds)
            except SignatureExpired:
                return None

        return payload
