import { signIn } from "@/auth";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">Beans &amp; Co</h1>
        <p className="mt-1 text-sm text-neutral-500">Centro de control</p>
      </div>
      <form
        action={async () => {
          "use server";
          await signIn("google", { redirectTo: "/hoy" });
        }}
      >
        <button
          type="submit"
          className="rounded-md bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700"
        >
          Entrar con Google
        </button>
      </form>
    </main>
  );
}
