import { neon } from "@neondatabase/serverless";
import { drizzle } from "drizzle-orm/neon-http";
import * as schema from "@/db/schema";

// Single-business Neon connection. The app owns the database; there is no
// tenant/phone scope anywhere. DATABASE_URL is set per environment in Vercel.
const databaseUrl = process.env.DATABASE_URL;

export const sql = databaseUrl ? neon(databaseUrl) : null;

export const db = databaseUrl
  ? drizzle(neon(databaseUrl), { schema })
  : (null as unknown as ReturnType<typeof drizzle>);
