import { auth, signOut } from "@/auth";

// M0 placeholder dashboard. It only proves the authed shell is live and shows
// who is signed in. The real Hoy tiles land in M4 against the Neon reads of M3.
export default async function Hoy() {
  const session = await auth();
  return (
    <main className="min-h-screen p-6">
      <header className="flex items-center justify-between border-b border-neutral-200 pb-4">
        <div>
          <h1 className="text-xl font-semibold">Hoy</h1>
          <p className="text-sm text-neutral-500">Beans &amp; Co — centro de control</p>
        </div>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/login" });
          }}
        >
          <button type="submit" className="text-sm text-neutral-500 hover:text-neutral-900">
            Salir
          </button>
        </form>
      </header>
      <section className="mt-6">
        <p className="text-sm text-neutral-600">
          Sesión activa: <span className="font-medium">{session?.user?.email ?? "sin sesión"}</span>
        </p>
        <p className="mt-4 text-sm text-neutral-400">
          Shell M0 vivo. Los tiles de Hoy llegan en M4.
        </p>
      </section>
    </main>
  );
}
