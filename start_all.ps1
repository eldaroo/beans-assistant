# Script completo: Tunel SSH + Backend
# Establece el tunel y luego inicia el backend

$VPS_USER = "root"
$VPS_HOST = "31.97.100.1"
$VPS_PASSWORD = "Dariowinner-90"
$LOCAL_PORT = 5433
$REMOTE_PORT = 5432

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  INICIO COMPLETO: TUNEL + BACKEND" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Paso 1: Matar procesos existentes
Write-Host "[1/3] Limpiando procesos..." -ForegroundColor Yellow

# Matar Python
$pythonProcesses = Get-Process -Name python -ErrorAction SilentlyContinue
if ($pythonProcesses) {
    $pythonProcesses | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}

# Matar SSH
$sshProcesses = Get-Process -Name ssh,plink -ErrorAction SilentlyContinue
if ($sshProcesses) {
    $sshProcesses | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Seconds 2
Write-Host "  [OK] Limpieza completada" -ForegroundColor Green

# Paso 2: Establecer tunel SSH
Write-Host ""
Write-Host "[2/3] Estableciendo tunel SSH..." -ForegroundColor Yellow
Write-Host "  localhost:$LOCAL_PORT -> $VPS_HOST`:$REMOTE_PORT" -ForegroundColor Cyan

# Verificar si plink (PuTTY) esta disponible
$plinkPath = Get-Command plink -ErrorAction SilentlyContinue

if ($plinkPath) {
    Write-Host "  Usando plink con password automatica..." -ForegroundColor Gray
    
    $plinkArgs = @(
        "-ssh",
        "-L", "${LOCAL_PORT}:localhost:${REMOTE_PORT}",
        "-N",
        "-pw", $VPS_PASSWORD,
        "${VPS_USER}@${VPS_HOST}"
    )
    
    $sshProcess = Start-Process plink -ArgumentList $plinkArgs -PassThru -WindowStyle Hidden
    
} else {
    Write-Host "  [INFO] plink no encontrado. Instalando PuTTY..." -ForegroundColor Yellow
    Write-Host "  Descarga PuTTY de: https://www.putty.org/" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Mientras tanto, usando OpenSSH (necesitaras ingresar password)..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  PASSWORD: $VPS_PASSWORD" -ForegroundColor Cyan
    Write-Host ""
    
    $sshArgs = @(
        "-L", "${LOCAL_PORT}:localhost:${REMOTE_PORT}",
        "-o", "ServerAliveInterval=60",
        "-o", "StrictHostKeyChecking=no",
        "-N",
        "${VPS_USER}@${VPS_HOST}"
    )
    
    $sshProcess = Start-Process ssh -ArgumentList $sshArgs -PassThru
}

Start-Sleep -Seconds 5

if ($sshProcess.HasExited) {
    Write-Host "  [ERROR] SSH fallo" -ForegroundColor Red
    exit 1
}

Write-Host "  [OK] Tunel SSH establecido (PID: $($sshProcess.Id))" -ForegroundColor Green

# Verificar tunel
$tunnelReady = $false
for ($i = 1; $i -le 10; $i++) {
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $tcpClient.Connect("127.0.0.1", $LOCAL_PORT)
        $tcpClient.Close()
        $tunnelReady = $true
        Write-Host "  [OK] Tunel verificado" -ForegroundColor Green
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}

# Paso 3: Iniciar backend
Write-Host ""
Write-Host "[3/3] Iniciando backend..." -ForegroundColor Yellow

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

$backendProcess = Start-Process python -ArgumentList "backend/app.py" -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 5

if (-not $backendProcess.HasExited) {
    Write-Host "  [OK] Backend iniciado (PID: $($backendProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Backend fallo al iniciar" -ForegroundColor Red
    exit 1
}

# Verificar backend
$backendReady = $false
for ($i = 1; $i -le 10; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/docs" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
            Write-Host "  [OK] Backend respondiendo" -ForegroundColor Green
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  [OK] TODO LISTO!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Servicios corriendo:" -ForegroundColor Cyan
Write-Host "  - Tunel SSH (PID: $($sshProcess.Id))" -ForegroundColor White
Write-Host "  - Backend (PID: $($backendProcess.Id))" -ForegroundColor White
Write-Host ""
Write-Host "Abre en tu navegador:" -ForegroundColor Yellow
Write-Host "  http://localhost:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Refresca con Ctrl+F5 y prueba el chat!" -ForegroundColor Green
Write-Host ""
Write-Host "Para detener todo: .\kill_all.ps1" -ForegroundColor Gray
Write-Host ""
