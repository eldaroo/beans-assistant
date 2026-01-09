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

# Paso 3: Abrir tunel SSH y verificar conexion
Write-Host ""
Write-Host "[3/4] Abriendo tunel SSH..." -ForegroundColor Yellow
Write-Host "  localhost:$LOCAL_PORT -> $VPS_HOST`:$REMOTE_PORT" -ForegroundColor Cyan

# Iniciar SSH en segundo plano
$sshProcess = Start-Process ssh -ArgumentList @(
    "-L", "${LOCAL_PORT}:localhost:${REMOTE_PORT}",
    "-o", "ServerAliveInterval=60",
    "-o", "ServerAliveCountMax=3",
    "-o", "ExitOnForwardFailure=yes",
    "-N",
    "$VPS_USER@$VPS_HOST"
) -PassThru -WindowStyle Hidden

# Esperar y verificar que el tunel este realmente conectado
Write-Host "  Esperando conexion SSH..." -ForegroundColor Gray
$maxAttempts = 10
$attempt = 0
$tunnelReady = $false

while ($attempt -lt $maxAttempts -and -not $tunnelReady) {
    Start-Sleep -Seconds 1
    $attempt++
    
    # Verificar si el proceso SSH sigue vivo
    if ($sshProcess.HasExited) {
        Write-Host "  [ERROR] Proceso SSH termino inesperadamente" -ForegroundColor Red
        Write-Host "  Verifica tus credenciales SSH o conectividad" -ForegroundColor Yellow
        exit 1
    }
    
    # Intentar conectar al puerto local para verificar que el tunel funciona
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $tcpClient.Connect("localhost", $LOCAL_PORT)
        $tcpClient.Close()
        $tunnelReady = $true
        Write-Host "  [OK] Tunel SSH establecido y verificado (PID: $($sshProcess.Id))" -ForegroundColor Green
    } catch {
        Write-Host "  Intento $attempt/$maxAttempts..." -ForegroundColor Gray
    }
}

if (-not $tunnelReady) {
    Write-Host "  [ERROR] No se pudo verificar el tunel SSH despues de $maxAttempts intentos" -ForegroundColor Red
    Write-Host "  El tunel puede estar activo pero PostgreSQL no responde en el puerto remoto" -ForegroundColor Yellow
    Write-Host "  Continuando de todas formas..." -ForegroundColor Yellow
}

# Paso 4: Iniciar backend
Write-Host ""
Write-Host "[4/4] Iniciando backend..." -ForegroundColor Yellow

# Cambiar al directorio del proyecto
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

# Iniciar backend en segundo plano
$backendProcess = Start-Process python -ArgumentList "backend/app.py" -PassThru -WindowStyle Hidden -RedirectStandardOutput "backend_output.log" -RedirectStandardError "backend_error.log"

# Esperar a que el backend inicie
Write-Host "  Esperando que el backend inicie..." -ForegroundColor Gray
Start-Sleep -Seconds 5

# Verificar que el backend esta corriendo
if (-not $backendProcess.HasExited) {
    Write-Host "  [OK] Backend iniciado (PID: $($backendProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Backend fallo al iniciar" -ForegroundColor Red
    Write-Host "  Revisa backend_error.log para mas detalles" -ForegroundColor Yellow
    exit 1
}

# Verificar que el backend responde
Write-Host "  Verificando que el backend responde..." -ForegroundColor Gray
$backendReady = $false
$maxAttempts = 10
$attempt = 0

while ($attempt -lt $maxAttempts -and -not $backendReady) {
    Start-Sleep -Seconds 1
    $attempt++
    
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/docs" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
            Write-Host "  [OK] Backend respondiendo correctamente" -ForegroundColor Green
        }
    } catch {
        Write-Host "  Intento $attempt/$maxAttempts..." -ForegroundColor Gray
    }
}

if (-not $backendReady) {
    Write-Host "  [WARNING] Backend no responde en http://localhost:8000" -ForegroundColor Yellow
    Write-Host "  Puede estar iniciando todavia. Revisa los logs." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  [OK] BACKEND REINICIADO EXITOSAMENTE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Servicios corriendo:" -ForegroundColor Cyan
Write-Host "  - Tunel SSH: localhost:$LOCAL_PORT -> $VPS_HOST`:$REMOTE_PORT (PID: $($sshProcess.Id))" -ForegroundColor White
Write-Host "  - Backend: http://localhost:8000 (PID: $($backendProcess.Id))" -ForegroundColor White
Write-Host ""
Write-Host "Logs del backend:" -ForegroundColor Yellow
Write-Host "  - Output: backend_output.log" -ForegroundColor Gray
Write-Host "  - Errors: backend_error.log" -ForegroundColor Gray
Write-Host ""
Write-Host "Para ver logs en tiempo real:" -ForegroundColor Yellow
Write-Host "  Get-Content backend_error.log -Wait" -ForegroundColor Gray
Write-Host ""
Write-Host "Para detener todo:" -ForegroundColor Yellow
Write-Host "  .\kill_all.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "Ahora puedes:" -ForegroundColor Cyan
Write-Host "  1. Abrir http://localhost:8000 en tu navegador" -ForegroundColor White
Write-Host "  2. Refrescar con Ctrl+F5 para recargar el JavaScript" -ForegroundColor White
Write-Host "  3. Probar el chat widget" -ForegroundColor White
Write-Host ""
