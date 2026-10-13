"""Control Center providers over the existing business surfaces.

Each provider is a thin tenant-scoped wrapper (``with tenant_scope(phone)``)
around a pure compute helper that turns already-fetched service data into a
Headline or a list of AttentionItem. The split keeps the data-meaning helpers
unit-testable with seeded rows (AC2) while the scoping stays plumbing.
"""
