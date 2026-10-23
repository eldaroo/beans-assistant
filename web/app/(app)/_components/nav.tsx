"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

// NAV_ITEMS lives in ./nav-items (a server-safe module) and is imported there by
// the server layout. A data export in this "use client" file resolved to a
// client-reference stub across the boundary, so NAV_ITEMS.map threw on the server.

export function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <Link
      href={href}
      className={
        "block rounded-md px-3 py-2 text-sm transition-colors " +
        (active
          ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
          : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800")
      }
    >
      {label}
    </Link>
  );
}
