-- Migration: Add function to get all tenant stats efficiently
-- This function queries all tenant schemas in parallel and returns aggregated stats

CREATE OR REPLACE FUNCTION get_all_tenant_stats()
RETURNS TABLE (
    schema_name TEXT,
    products_count BIGINT,
    sales_count BIGINT,
    revenue_cents BIGINT,
    profit_usd NUMERIC
) AS $$
DECLARE
    tenant_schema TEXT;
BEGIN
    -- Loop through all schemas that start with 'tenant_'
    FOR tenant_schema IN
        SELECT nspname
        FROM pg_namespace
        WHERE nspname LIKE 'tenant_%' OR nspname = 'public'
    LOOP
        BEGIN
            -- Get stats for this tenant schema
            RETURN QUERY EXECUTE format('
                SELECT
                    %L::TEXT as schema_name,
                    (SELECT COUNT(*) FROM %I.products)::BIGINT as products_count,
                    (SELECT COUNT(*) FROM %I.sales WHERE status = ''PAID'')::BIGINT as sales_count,
                    (SELECT COALESCE(SUM(total_amount_cents), 0) FROM %I.sales WHERE status = ''PAID'')::BIGINT as revenue_cents,
                    (
                        SELECT
                            (COALESCE(r.total_revenue_cents, 0) - COALESCE(e.total_expenses_cents, 0)) / 100.0
                        FROM
                            (SELECT COALESCE(SUM(total_amount_cents), 0) as total_revenue_cents
                             FROM %I.sales WHERE status = ''PAID'') r,
                            (SELECT COALESCE(SUM(amount_cents), 0) as total_expenses_cents
                             FROM %I.expenses) e
                    )::NUMERIC as profit_usd
            ', tenant_schema, tenant_schema, tenant_schema, tenant_schema, tenant_schema, tenant_schema);
        EXCEPTION
            WHEN undefined_table THEN
                -- Schema exists but tables don't exist yet, skip
                CONTINUE;
            WHEN OTHERS THEN
                -- Log error and continue
                RAISE NOTICE 'Error querying schema %: %', tenant_schema, SQLERRM;
                CONTINUE;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execute permission to the application user
GRANT EXECUTE ON FUNCTION get_all_tenant_stats() TO beansco;

-- Add index to improve performance (if not already exists)
-- These indexes help the COUNT(*) and SUM() operations
DO $$
BEGIN
    -- Note: Indexes need to be created per schema, not globally
    -- This is just a reminder/template
    RAISE NOTICE 'Remember to create indexes on each tenant schema for optimal performance';
    RAISE NOTICE 'CREATE INDEX IF NOT EXISTS idx_sales_status ON sales(status);';
END $$;
