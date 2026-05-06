"""Data access for public.app_users (portal authorization)."""

import os
from datetime import datetime, timezone
from typing import Optional


class AppUsersRepository:
    """CRUD for app_users. Always queries public schema, never tenant-scoped."""

    @staticmethod
    def _connect():
        import psycopg2
        from psycopg2.extras import RealDictCursor
        return psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "beansco_main"),
            user=os.getenv("POSTGRES_USER", "beansco"),
            password=os.getenv("POSTGRES_PASSWORD", "changeme123"),
            cursor_factory=RealDictCursor,
            options="-c client_encoding=UTF8",
        )

    def get_by_email(self, email: str) -> Optional[dict]:
        normalized = (email or "").strip().lower()
        if not normalized:
            return None
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, google_email, phone_number, role, created_at, last_login_at
                    FROM public.app_users
                    WHERE google_email = %s
                    """,
                    (normalized,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def create(self, email: str, phone_number: str, role: str = "owner") -> dict:
        normalized_email = email.strip().lower()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.app_users (google_email, phone_number, role)
                    VALUES (%s, %s, %s)
                    RETURNING id, google_email, phone_number, role, created_at, last_login_at
                    """,
                    (normalized_email, phone_number, role),
                )
                row = cur.fetchone()
            conn.commit()
            return dict(row)
        finally:
            conn.close()

    def update_last_login(self, user_id: int) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.app_users SET last_login_at = %s WHERE id = %s",
                    (datetime.now(timezone.utc), user_id),
                )
            conn.commit()
        finally:
            conn.close()

    def tenant_exists(self, phone_number: str) -> bool:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM public.tenants WHERE phone_number = %s",
                    (phone_number,),
                )
                return cur.fetchone() is not None
        finally:
            conn.close()
