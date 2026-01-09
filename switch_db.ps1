# Script para cambiar rapidamente entre SQLite y PostgreSQL

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("sqlite", "postgres")]
    [string]$Mode = "sqlite"
)

$envFile = ".env"

if (-not (Test-Path $envFile)) {
    Write-Host "[ERROR] Archivo .env no encontrado" -ForegroundColor Red
    Write-Host "Copia .env.example a .env primero" -ForegroundColor Yellow
    exit 1
}

Write-Host "Cambiando a modo: $Mode" -ForegroundColor Cyan
Write-Host ""

# Leer el archivo .env
$content = Get-Content $envFile -Raw

if ($Mode -eq "sqlite") {
    # Cambiar a SQLite
    $content = $content -replace "USE_POSTGRES=true", "USE_POSTGRES=false"
    Write-Host "[OK] Configurado para usar SQLite" -ForegroundColor Green
    Write-Host "  - Mas rapido para desarrollo local" -ForegroundColor Gray
    Write-Host "  - No requiere tunel SSH" -ForegroundColor Gray
} else {
    # Cambiar a PostgreSQL
    $content = $content -replace "USE_POSTGRES=false", "USE_POSTGRES=true"
    Write-Host "[OK] Configurado para usar PostgreSQL" -ForegroundColor Green
    Write-Host "  - Requiere tunel SSH activo" -ForegroundColor Gray
    Write-Host "  - Mas lento pero para produccion" -ForegroundColor Gray
}

# Guardar cambios
$content | Set-Content $envFile -NoNewline

Write-Host ""
Write-Host "IMPORTANTE: Reinicia el backend para aplicar cambios" -ForegroundColor Yellow
Write-Host "  .\kill_all.ps1" -ForegroundColor Gray
Write-Host "  python backend/app.py" -ForegroundColor Gray
Write-Host ""
