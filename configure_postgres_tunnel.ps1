# Script para configurar PostgreSQL para tunel SSH

$envFile = ".env"

Write-Host "Configurando PostgreSQL para tunel SSH..." -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $envFile)) {
    Write-Host "[ERROR] Archivo .env no encontrado" -ForegroundColor Red
    exit 1
}

# Leer archivo
$content = Get-Content $envFile -Raw

# Configurar para tunel SSH local
$content = $content -replace 'POSTGRES_HOST=postgres', 'POSTGRES_HOST=localhost'
$content = $content -replace 'POSTGRES_PORT=5432', 'POSTGRES_PORT=5433'

# Guardar con UTF-8 sin BOM
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($envFile, $content, $utf8NoBom)

Write-Host "[OK] Configuracion actualizada:" -ForegroundColor Green
Write-Host "  POSTGRES_HOST=localhost (para tunel SSH)" -ForegroundColor Gray
Write-Host "  POSTGRES_PORT=5433 (puerto del tunel local)" -ForegroundColor Gray
Write-Host ""
Write-Host "Ahora:" -ForegroundColor Yellow
Write-Host "  1. Asegurate de que el tunel SSH este activo" -ForegroundColor White
Write-Host "  2. Reinicia el backend" -ForegroundColor White
Write-Host ""
