-- Allow products.unit_price_cents to be NULL (precio pendiente).
-- A product can be created from chat without a known sale price; the price
-- is filled later (post-creation prompt or first sale).
--
-- Rollback (manual, only if no NULL rows exist):
--   ALTER TABLE products DROP CONSTRAINT check_unit_price_positive;
--   ALTER TABLE products ADD CONSTRAINT check_unit_price_positive
--     CHECK (unit_price_cents >= 0);
--   ALTER TABLE products ALTER COLUMN unit_price_cents SET NOT NULL;

ALTER TABLE products ALTER COLUMN unit_price_cents DROP NOT NULL;

ALTER TABLE products DROP CONSTRAINT IF EXISTS check_unit_price_positive;

ALTER TABLE products ADD CONSTRAINT check_unit_price_positive
    CHECK (unit_price_cents IS NULL OR unit_price_cents >= 0);
