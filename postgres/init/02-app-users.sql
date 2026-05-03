-- App users for Google OAuth login to the customer portal.
-- One row per authorized human; phone_number maps the user to their tenant.

-- Mirror of the tenants table that tenant_manager._ensure_tenants_table() creates
-- at app startup, so the FK below has a target on a fresh DB init. Both definitions
-- are idempotent and must stay aligned.
CREATE TABLE IF NOT EXISTS public.tenants (
    phone_number    TEXT PRIMARY KEY,
    business_name   TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    config          JSONB,
    whatsapp_lid    TEXT
);

CREATE INDEX IF NOT EXISTS idx_tenants_whatsapp_lid
    ON public.tenants(whatsapp_lid)
    WHERE whatsapp_lid IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.app_users (
    id              BIGSERIAL PRIMARY KEY,
    google_email    TEXT NOT NULL UNIQUE,
    phone_number    TEXT NOT NULL UNIQUE,
    role            TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'admin')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ,

    CONSTRAINT fk_app_users_tenant
        FOREIGN KEY (phone_number)
        REFERENCES public.tenants(phone_number)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_app_users_google_email ON public.app_users(google_email);
CREATE INDEX IF NOT EXISTS idx_app_users_phone_number ON public.app_users(phone_number);

DO $$
BEGIN
    RAISE NOTICE 'app_users table ready';
END $$;
