import NextAuth from "next-auth";
import { authConfig } from "./auth.config";

// The middleware runs the edge-safe auth config: it protects every page route
// and redirects an unauthenticated visitor to /login (Google OAuth).
export const { auth: middleware } = NextAuth(authConfig);

export const config = {
  // Run on everything except Next internals, the auth API, and static files.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
