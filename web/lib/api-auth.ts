// Shared guard for read routes: requires a signed-in session and a configured DB.
// Returns null when OK, or the envelope response to return early.
import { auth } from "@/auth";
import { fail, requireDb } from "@/lib/http";
import type { NextResponse } from "next/server";

export async function guard(): Promise<NextResponse | null> {
  const session = await auth();
  if (!session?.user) return fail("unauthorized", "Sign in required", 401);
  return requireDb();
}
