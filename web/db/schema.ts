// Drizzle schema for the single-business Beans database.
// M0 ships an empty schema so the client compiles; M1 fills the nine domains
// (products, stock, sales, expenses, costing, cost scenarios, production,
// suppliers, logistics) plus the append-only audit_log. No tenant columns.
export {};
