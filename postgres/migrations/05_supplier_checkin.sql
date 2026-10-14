-- spec 003 M5 (T-018/AC13): add the supplier check-in timestamp per tenant schema.
-- last_checkin_at is the last recorded check-in/reply from a supplier; the overdue
-- attention signal reads it from stored data with no message sent. Idempotent.
-- Run per-schema (set search_path first); the forward loop lives in
-- run_05_supplier_checkin.py.
ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS last_checkin_at TIMESTAMP;
