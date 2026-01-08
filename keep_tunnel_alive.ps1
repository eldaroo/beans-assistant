# Script para mantener túnel SSH siempre activo
# Se reconecta automáticamente si se cae

$VPS_USER = "root"
$VPS_HOST = "31.97.100.1"
$LOCAL_PORT = 5433
$REMOTE_PORT = 5432

Write-Host "Manteniendo túnel SSH activo..." -ForegroundColor Green
Write-Host "localhost:$LOCAL_PORT -> $VPS_HOST`:$REMOTE_PORT" -ForegroundColor Cyan
Write-Host "Presiona Ctrl+C para detener" -ForegroundColor Yellow
Write-Host ""

while ($true) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Conectando túnel SSH..." -ForegroundColor Gray

    # Crear túnel SSH con opciones para mantenerlo vivo
    ssh -L ${LOCAL_PORT}:localhost:${REMOTE_PORT} `
        -o ServerAliveInterval=60 `
        -o ServerAliveCountMax=3 `
        -o ExitOnForwardFailure=yes `
        -N $VPS_USER@$VPS_HOST

    # Si llegamos aquí, el túnel se cayó
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Túnel desconectado. Reconectando en 5 segundos..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
