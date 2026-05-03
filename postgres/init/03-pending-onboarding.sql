-- Pending onboarding sessions: per-email scratchpad for the LLM-driven
-- onboarding flow. Holds the partial captured `state`, the truncated
-- conversation `history`, and a turn counter. One row per pending email.
-- Lazy-deleted on first read of an expired row (per ADR-002).

CREATE TABLE IF NOT EXISTS public.pending_onboarding_sessions (
    email           TEXT PRIMARY KEY,
    state           JSONB NOT NULL DEFAULT '{}'::jsonb,
    history         JSONB NOT NULL DEFAULT '[]'::jsonb,
    turn_count      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at),
    CHECK (jsonb_array_length(history) <= 12)
);

CREATE INDEX IF NOT EXISTS idx_pos_expires
    ON public.pending_onboarding_sessions(expires_at);

DO $$
BEGIN
    RAISE NOTICE 'pending_onboarding_sessions table ready';
END $$;
