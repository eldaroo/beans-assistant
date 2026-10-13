"""Beans Control Center module system.

The command-center shell. A static registry holds one descriptor per business
domain, each exposing two read-only providers: a ``headline`` (the module's one
number for its home tile) and ``attention`` (the module's list of items for the
strip). The status home iterates the registry; it owns no domain logic.

Spec: specs/003-production-landed-cost-engine/spec.md (Beans Control Center, M1).
Contract: ARCHITECTURE.md D-020 through D-023.
"""
