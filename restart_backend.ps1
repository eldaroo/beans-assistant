# Script para reiniciar completamente el backend
# Mata todas las instancias, abre tunel SSH y lanza backend limpio

$VPS_USER = "root"
$VPS_HOST = "31.97.100.1"
$LOCAL_PORT = 5433
$REMOTE_PORT = 5432

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  REINICIO COMPLETO DEL BACKEND" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Paso 1: Matar todas las instancias de Python (backend)
Write-Host "[1/4] Matando instancias del backend..." -ForegroundColor Yellow
$pythonProcesses = Get-Process -Name python -ErrorAction SilentlyContinue
if ($pythonProcesses) {
    $pythonProcesses | ForEach-Object {
        Write-Host "  Matando proceso Python (PID: $($_.Id))..." -ForegroundColor Gray
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  [OK] Procesos Python terminados" -ForegroundColor Green
} else {
    Write-Host "  [OK] No hay procesos Python corriendo" -ForegroundColor Green
}

# Paso 2: Matar tuneles SSH existentes
Write-Host ""
Write-Host "[2/4] Matando tuneles SSH existentes..." -ForegroundColor Yellow
$sshProcesses = Get-Process -Name ssh -ErrorAction SilentlyContinue
if ($sshProcesses) {
    $sshProcesses | ForEach-Object {
        Write-Host "  Matando proceso SSH (PID: $($_.Id))..." -ForegroundColor Gray
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  [OK] Tuneles SSH terminados" -ForegroundColor Green
} else {
    Write-Host "  [OK] No hay tuneles SSH corriendo" -ForegroundColor Green
}

# Esperar un momento para que los puertos se liberen
Start-Sleep -Seconds 2

# Paso 3: Abrir tunel SSH en segundo plano
Write-Host ""
Write-Host "[3/4] Abriendo tunel SSH..." -ForegroundColor Yellow
Write-Host "  localhost:$LOCAL_PORT -> $VPS_HOST`:$REMOTE_PORT" -ForegroundColor Cyan

# Crear tunel SSH en segundo plano
$sshJob = Start-Job -ScriptBlock {
    param($vpsUser, $vpsHost, $localPort, $remotePort)
    ssh -L ${localPort}:localhost:${remotePort} `
        -o ServerAliveInterval=60 `
        -o ServerAliveCountMax=3 `
        -o ExitOnForwardFailure=yes `
        -N "$vpsUser@$vpsHost"
} -ArgumentList $VPS_USER, $VPS_HOST, $LOCAL_PORT, $REMOTE_PORT

# Esperar a que el tunel se establezca
Start-Sleep -Seconds 3

# Verificar que el tunel esta activo
$sshProcess = Get-Process -Name ssh -ErrorAction SilentlyContinue
if ($sshProcess) {
    Write-Host "  [OK] Tunel SSH establecido (PID: $($sshProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Error al establecer tunel SSH" -ForegroundColor Red
    Write-Host "  Verifica tus credenciales SSH" -ForegroundColor Yellow
    exit 1
}

# Paso 4: Iniciar backend
Write-Host ""
Write-Host "[4/4] Iniciando backend..." -ForegroundColor Yellow

# Cambiar al directorio del proyecto
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

# Iniciar backend en segundo plano
$backendJob = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    python backend/app.py
} -ArgumentList $projectDir

# Esperar a que el backend inicie
Start-Sleep -Seconds 3

# Verificar que el backend esta corriendo
$pythonProcess = Get-Process -Name python -ErrorAction SilentlyContinue
if ($pythonProcess) {
    Write-Host "  [OK] Backend iniciado (PID: $($pythonProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Error al iniciar backend" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  [OK] BACKEND REINICIADO EXITOSAMENTE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Servicios corriendo:" -ForegroundColor Cyan
Write-Host "  - Tunel SSH: localhost:$LOCAL_PORT -> $VPS_HOST`:$REMOTE_PORT" -ForegroundColor White
Write-Host "  - Backend: http://localhost:8000" -ForegroundColor White
Write-Host ""
Write-Host "Para ver logs del backend:" -ForegroundColor Yellow
Write-Host "  Receive-Job -Id $($backendJob.Id) -Keep" -ForegroundColor Gray
Write-Host ""
Write-Host "Para detener todo:" -ForegroundColor Yellow
Write-Host "  1. Mata procesos Python: Get-Process python | Stop-Process -Force" -ForegroundColor Gray
Write-Host "  2. Mata tunel SSH: Get-Process ssh | Stop-Process -Force" -ForegroundColor Gray
Write-Host ""
Write-Host "Presiona Ctrl+C para salir (los servicios seguiran corriendo)" -ForegroundColor Cyan
Write-Host ""

# Mantener el script vivo y mostrar logs
Write-Host "Mostrando logs del backend (Ctrl+C para salir)..." -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Gray
Write-Host ""

# Mostrar logs en tiempo real
while ($true) {
    $output = Receive-Job -Id $backendJob.Id
    if ($output) {
        Write-Host $output
    }
    
    # Verificar si el backend sigue vivo
    $pythonProcess = Get-Process -Name python -ErrorAction SilentlyContinue
    if (-not $pythonProcess) {
        Write-Host ""
        Write-Host "[ERROR] Backend se detuvo inesperadamente" -ForegroundColor Red
        break
    }
    
    Start-Sleep -Seconds 1
}
