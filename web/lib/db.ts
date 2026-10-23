import { Pool } from "@neondatabase/serverless";
import { drizzle } from "drizzle-orm/neon-serverless";
import * as schema from "@/db/schema";

// Single-business Neon connection. The app owns the database; there is no
// tenant/phone scope anywhere. DATABASE_URL is set per environment in Vercel.
//
// The neon-serverless Pool (WebSocket) driver is used rather than neon-http so
// that multi-statement writes (a sale insert + its line items + stock movements)
// commit inside one real transaction via db.transaction(). It runs on Vercel's
// Node serverless runtime out of the box.
const databaseUrl = process.env.DATABASE_URL;

const pool = databaseUrl ? new Pool({ connectionString: databaseUrl }) : null;

export const db = pool
  ? drizzle(pool, { schema })
  : (null as unknown as ReturnType<typeof drizzle<typeof schema>>);
