# Apply migration directly on VPS via SSH
# This bypasses the encoding issue by running commands directly on the server

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Apply Migration via SSH" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$VPS_USER = "root"
$VPS_HOST = "31.97.100.1"
$VPS_PORT = 22

Write-Host "Connecting to VPS: $VPS_USER@$VPS_HOST" -ForegroundColor Yellow
Write-Host ""

# Create a temporary SQL file with the migration
Write-Host "Step 1: Creating temporary migration file..." -ForegroundColor Green

$migrationSQL = @"
-- Tenant Stats Optimization Function
CREATE OR REPLACE FUNCTION get_all_tenant_stats()
RETURNS TABLE (
    schema_name TEXT,
    products_count BIGINT,
    sales_count BIGINT,
    revenue_cents BIGINT,
    profit_usd NUMERIC
) AS `$`$
DECLARE
    tenant_schema TEXT;
BEGIN
    FOR tenant_schema IN
        SELECT nspname
        FROM pg_namespace
        WHERE nspname LIKE 'tenant_%' OR nspname = 'public'
    LOOP
        BEGIN
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
                CONTINUE;
            WHEN OTHERS THEN
                RAISE NOTICE 'Error querying schema %: %', tenant_schema, SQLERRM;
                CONTINUE;
        END;
    END LOOP;
END;
`$`$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION get_all_tenant_stats() TO beansco;
"@

# Save to temp file
$tempFile = ".\temp_migration.sql"
$migrationSQL | Out-File -FilePath $tempFile -Encoding UTF8 -NoNewline

Write-Host "  Created: $tempFile" -ForegroundColor Gray
Write-Host ""

# Copy file to VPS
Write-Host "Step 2: Copying migration to VPS..." -ForegroundColor Green
scp -P $VPS_PORT $tempFile ${VPS_USER}@${VPS_HOST}:/tmp/migration.sql

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Failed to copy file to VPS" -ForegroundColor Red
    Remove-Item $tempFile
    exit 1
}

Write-Host "  File copied successfully" -ForegroundColor Gray
Write-Host ""

# Execute on VPS
Write-Host "Step 3: Executing migration on VPS..." -ForegroundColor Green
Write-Host ""

$sshCommand = @"
PGPASSWORD='changeme123' psql -h localhost -U beansco -d beansco_main -f /tmp/migration.sql && echo '==MIGRATION_SUCCESS=='
"@

ssh -p $VPS_PORT ${VPS_USER}@${VPS_HOST} $sshCommand

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "MIGRATION APPLIED SUCCESSFULLY!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Restart your backend: .\restart_backend.ps1" -ForegroundColor White
    Write-Host "  2. Visit http://localhost:8000/ to see improved performance" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "ERROR: Migration failed" -ForegroundColor Red
    Write-Host "Check the output above for details" -ForegroundColor Yellow
}

# Cleanup
Write-Host "Cleaning up..." -ForegroundColor Gray
Remove-Item $tempFile -ErrorAction SilentlyContinue
ssh -p $VPS_PORT ${VPS_USER}@${VPS_HOST} "rm -f /tmp/migration.sql" 2>$null

Write-Host "Done!" -ForegroundColor Green
