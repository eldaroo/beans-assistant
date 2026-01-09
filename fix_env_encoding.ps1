# Script para arreglar el encoding del archivo .env

$envFile = ".env"

Write-Host "Arreglando encoding del archivo .env..." -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $envFile)) {
    Write-Host "[ERROR] Archivo .env no encontrado" -ForegroundColor Red
    exit 1
}

# Leer el archivo con encoding correcto
try {
    # Intentar leer con UTF-8
    $content = Get-Content $envFile -Encoding UTF8 -Raw
    Write-Host "[OK] Archivo leido correctamente" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] Error leyendo con UTF-8, intentando con Default..." -ForegroundColor Yellow
    $content = Get-Content $envFile -Raw
}

# Guardar con UTF-8 sin BOM
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($envFile, $content, $utf8NoBom)

Write-Host "[OK] Archivo guardado con UTF-8 sin BOM" -ForegroundColor Green
Write-Host ""
Write-Host "Ahora verifica la configuracion de PostgreSQL:" -ForegroundColor Cyan
Write-Host ""

# Mostrar configuracion actual
$postgresLines = Get-Content $envFile | Select-String "POSTGRES"
foreach ($line in $postgresLines) {
    Write-Host "  $line" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Si la password tiene caracteres especiales, asegurate de que sean ASCII" -ForegroundColor Yellow
Write-Host "Evita: ñ, á, é, í, ó, ú, ü, etc." -ForegroundColor Gray
Write-Host ""
