"""Admin CLI for the customer portal.

Usage:
    python -m backend.cli grant_access --email user@gmail.com --phone +5491153695627 [--role owner|admin]
    python -m backend.cli revoke_access --email user@gmail.com
    python -m backend.cli list_users
"""

import argparse
import sys

from backend.repositories.app_users_repository import AppUsersRepository


def cmd_grant_access(args):
    repo = AppUsersRepository()

    if args.role not in ("owner", "admin"):
        print(f"ERROR: invalid role '{args.role}' (use owner or admin)", file=sys.stderr)
        return 2

    if args.role == "owner" and not repo.tenant_exists(args.phone):
        print(f"ERROR: tenant {args.phone} does not exist in public.tenants", file=sys.stderr)
        return 2

    existing = repo.get_by_email(args.email)
    if existing:
        print(
            f"ERROR: email {args.email} already mapped to tenant "
            f"{existing['phone_number']} (role={existing['role']})",
            file=sys.stderr,
        )
        return 2

    user = repo.create(args.email, args.phone, role=args.role)
    print(f"OK: granted {args.role} access to {user['google_email']} -> {user['phone_number']}")
    return 0


def cmd_revoke_access(args):
    import os
    repo = AppUsersRepository()
    user = repo.get_by_email(args.email)
    if not user:
        print(f"ERROR: no user with email {args.email}", file=sys.stderr)
        return 2

    conn = repo._connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.app_users WHERE id = %s", (user["id"],))
        conn.commit()
    finally:
        conn.close()
    print(f"OK: revoked access for {args.email}")
    return 0


def cmd_list_users(args):
    repo = AppUsersRepository()
    conn = repo._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT google_email, phone_number, role, created_at, last_login_at
                FROM public.app_users
                ORDER BY created_at
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        print("(no users)")
        return 0

    for row in rows:
        last = row["last_login_at"].isoformat() if row["last_login_at"] else "never"
        print(f"{row['google_email']:40s}  {row['phone_number']:18s}  {row['role']:6s}  last={last}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="backend.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("grant_access", help="Authorize an email to access a tenant portal")
    g.add_argument("--email", required=True)
    g.add_argument("--phone", required=True, help="Tenant phone in international format, e.g. +5491153695627")
    g.add_argument("--role", default="owner", help="owner (default) or admin")
    g.set_defaults(func=cmd_grant_access)

    r = sub.add_parser("revoke_access", help="Remove portal access for an email")
    r.add_argument("--email", required=True)
    r.set_defaults(func=cmd_revoke_access)

    l = sub.add_parser("list_users", help="List all portal users")
    l.set_defaults(func=cmd_list_users)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
