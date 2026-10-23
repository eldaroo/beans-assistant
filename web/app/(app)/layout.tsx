import { redirect } from "next/navigation";
import { auth } from "@/auth";

// Server-side auth guard for every page in the (app) route group. Replaces the
// edge middleware (Next 15.5 packages middleware as a Node lambda that fails to
// load as ESM). An unauthenticated visitor is sent to /login.
export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) {
    redirect("/login");
  }
  return <>{children}</>;
}
