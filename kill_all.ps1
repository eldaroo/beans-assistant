# Script simple para matar TODAS las instancias del backend y tuneles SSH
# Util cuando necesitas limpiar todo antes de reiniciar

Write-Host "========================================" -ForegroundColor Red
Write-Host "  MATANDO TODOS LOS SERVICIOS" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Red
Write-Host ""

# Matar Python (backend)
Write-Host "[1/2] Matando procesos Python..." -ForegroundColor Yellow
$pythonProcesses = Get-Process -Name python -ErrorAction SilentlyContinue
if ($pythonProcesses) {
    $pythonProcesses | ForEach-Object {
        Write-Host "  Matando Python (PID: $($_.Id))..." -ForegroundColor Gray
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  [OK] Procesos Python terminados" -ForegroundColor Green
} else {
    Write-Host "  [OK] No hay procesos Python corriendo" -ForegroundColor Green
}

# Matar SSH (tuneles)
Write-Host ""
Write-Host "[2/2] Matando tuneles SSH..." -ForegroundColor Yellow
$sshProcesses = Get-Process -Name ssh -ErrorAction SilentlyContinue
if ($sshProcesses) {
    $sshProcesses | ForEach-Object {
        Write-Host "  Matando SSH (PID: $($_.Id))..." -ForegroundColor Gray
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  [OK] Tuneles SSH terminados" -ForegroundColor Green
} else {
    Write-Host "  [OK] No hay tuneles SSH corriendo" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  [OK] TODOS LOS SERVICIOS DETENIDOS" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Ahora puedes ejecutar: .\restart_backend.ps1" -ForegroundColor Cyan
