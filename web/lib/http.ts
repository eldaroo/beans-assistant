// Named-error response envelope (spec 008 AC: every HTTP endpoint returns
// {ok:true,data} or {ok:false,error:{code,message}}).
import { NextResponse } from "next/server";

export function ok<T>(data: T, status = 200) {
  return NextResponse.json({ ok: true, data }, { status });
}

export function fail(code: string, message: string, status = 400) {
  return NextResponse.json({ ok: false, error: { code, message } }, { status });
}

// Guard: the app must have a database. Returns a 503 envelope when DATABASE_URL
// is unset (e.g. a misconfigured preview), never a raw 500.
export function requireDb(): NextResponse | null {
  if (!process.env.DATABASE_URL) {
    return fail("no_database", "DATABASE_URL is not configured", 503);
  }
  return null;
}
