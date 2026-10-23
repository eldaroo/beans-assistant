import { redirect } from "next/navigation";
import { auth, signOut } from "@/auth";
import { NAV_ITEMS, NavLink } from "./_components/nav";
import { Chat } from "./_components/chat";

// Server-side auth guard for every page in the (app) route group, plus the
// command-center chrome (sidebar nav + sign-out). An unauthenticated visitor is
// sent to /login. (Next 15.5 packages middleware as a Node lambda that fails to
// load as ESM, so the guard lives here, not in middleware.)
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session?.user) redirect("/login");

  return (
    <div className="flex min-h-screen bg-neutral-50 dark:bg-neutral-950">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900 md:flex">
        <div className="mb-6 px-3">
          <div className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Beans &amp; Co</div>
          <div className="text-xs text-neutral-500">Centro de control</div>
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV_ITEMS.map(([href, label]) => (
            <NavLink key={href} href={href} label={label} />
          ))}
        </nav>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/login" });
          }}
          className="mt-4 border-t border-neutral-200 pt-4 dark:border-neutral-800"
        >
          <div className="px-3 text-xs text-neutral-400">{session.user.email}</div>
          <button type="submit" className="mt-1 px-3 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100">
            Salir
          </button>
        </form>
      </aside>
      <main className="flex-1 p-6 md:p-8">
        {/* Mobile top nav */}
        <div className="mb-4 flex gap-2 overflow-x-auto md:hidden">
          {NAV_ITEMS.map(([href, label]) => (
            <NavLink key={href} href={href} label={label} />
          ))}
        </div>
        {children}
      </main>
      <Chat />
    </div>
  );
}
