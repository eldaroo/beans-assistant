import type { NextAuthConfig } from "next-auth";

// Edge-safe auth config shared by the middleware and the full NextAuth instance.
// It carries no provider (providers import Node crypto and cannot run at the
// edge); the full set lives in auth.ts. This file only owns route protection.
export const authConfig = {
  pages: { signIn: "/login" },
  providers: [],
  callbacks: {
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const isOnLogin = nextUrl.pathname.startsWith("/login");
      if (isOnLogin) {
        if (isLoggedIn) return Response.redirect(new URL("/hoy", nextUrl));
        return true;
      }
      return isLoggedIn;
    },
  },
} satisfies NextAuthConfig;
