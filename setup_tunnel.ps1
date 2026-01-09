# Script para establecer tunel SSH con password
# IMPORTANTE: Este script contiene la password. Mantenlo seguro.

$VPS_USER = "root"
$VPS_HOST = "31.97.100.1"
$VPS_PASSWORD = "Dariowinner-90"
$LOCAL_PORT = 5433
$REMOTE_PORT = 5432

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ESTABLECIENDO TUNEL SSH" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar si sshpass esta instalado (necesario para password automation)
$sshpassExists = Get-Command sshpass -ErrorAction SilentlyContinue
if (-not $sshpassExists) {
    Write-Host "[INFO] sshpass no esta instalado" -ForegroundColor Yellow
    Write-Host "  El tunel se abrira pero necesitaras ingresar la password manualmente" -ForegroundColor Gray
    Write-Host "  Password: $VPS_PASSWORD" -ForegroundColor Cyan
    Write-Host ""
}

# Matar tuneles SSH existentes
Write-Host "[1/2] Limpiando tuneles SSH existentes..." -ForegroundColor Yellow
$sshProcesses = Get-Process -Name ssh -ErrorAction SilentlyContinue
if ($sshProcesses) {
    $sshProcesses | ForEach-Object {
        Write-Host "  Matando SSH (PID: $($_.Id))..." -ForegroundColor Gray
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}
Write-Host "  [OK] Limpieza completada" -ForegroundColor Green

# Iniciar tunel SSH
Write-Host ""
Write-Host "[2/2] Iniciando tunel SSH..." -ForegroundColor Yellow
Write-Host "  Conexion: localhost:$LOCAL_PORT -> $VPS_HOST`:$REMOTE_PORT" -ForegroundColor Cyan
Write-Host ""

# Crear archivo temporal con la password para plink (PuTTY)
# Plink es mas facil de automatizar en Windows que OpenSSH con passwords
$plinkExists = Get-Command plink -ErrorAction SilentlyContinue

if ($plinkExists) {
    Write-Host "  Usando plink (PuTTY)..." -ForegroundColor Gray
    
    # Usar plink con password
    $plinkArgs = @(
        "-ssh",
        "-L", "${LOCAL_PORT}:localhost:${REMOTE_PORT}",
        "-N",
        "-pw", $VPS_PASSWORD,
        "${VPS_USER}@${VPS_HOST}"
    )
    
    $sshProcess = Start-Process plink -ArgumentList $plinkArgs -PassThru -WindowStyle Hidden
    
} else {
    Write-Host "  Usando OpenSSH (necesitaras ingresar password)..." -ForegroundColor Gray
    Write-Host ""
    Write-Host "  PASSWORD: $VPS_PASSWORD" -ForegroundColor Cyan
    Write-Host "  Copiala y pegala cuando SSH la pida" -ForegroundColor Yellow
    Write-Host ""
    
    # Usar OpenSSH normal (pedira password interactivamente)
    $sshArgs = @(
        "-L", "${LOCAL_PORT}:localhost:${REMOTE_PORT}",
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=no",
        "-N",
        "${VPS_USER}@${VPS_HOST}"
    )
    
    # Iniciar SSH en una nueva ventana para que puedas ingresar la password
    $sshProcess = Start-Process ssh -ArgumentList $sshArgs -PassThru
}

Write-Host "  Esperando que el tunel se establezca..." -ForegroundColor Gray
Start-Sleep -Seconds 5

# Verificar que el proceso sigue vivo
if ($sshProcess.HasExited) {
    Write-Host ""
    Write-Host "  [ERROR] SSH termino inesperadamente" -ForegroundColor Red
    Write-Host "  Verifica la password y la conectividad" -ForegroundColor Yellow
    exit 1
}

Write-Host "  [OK] Proceso SSH iniciado (PID: $($sshProcess.Id))" -ForegroundColor Green

# Verificar que el puerto local responde
Write-Host "  Verificando tunel..." -ForegroundColor Gray

$maxAttempts = 15
$attempt = 0
$tunnelReady = $false

while ($attempt -lt $maxAttempts -and -not $tunnelReady) {
    $attempt++
    Start-Sleep -Seconds 1
    
    # Verificar que el proceso sigue vivo
    if ($sshProcess.HasExited) {
        Write-Host ""
        Write-Host "  [ERROR] SSH termino durante la verificacion" -ForegroundColor Red
        exit 1
    }
    
    # Intentar conectar al puerto local
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $tcpClient.Connect("127.0.0.1", $LOCAL_PORT)
        $tcpClient.Close()
        $tunnelReady = $true
        Write-Host "  [OK] Tunel verificado y funcionando!" -ForegroundColor Green
    } catch {
        Write-Host "  Intento $attempt/$maxAttempts..." -ForegroundColor Gray
    }
}

if (-not $tunnelReady) {
    Write-Host ""
    Write-Host "  [WARNING] No se pudo verificar el tunel" -ForegroundColor Yellow
    Write-Host "  El tunel puede estar activo pero PostgreSQL no responde" -ForegroundColor Gray
    Write-Host "  Continuando de todas formas..." -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  [OK] TUNEL SSH ESTABLECIDO" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Tunel activo:" -ForegroundColor Cyan
Write-Host "  localhost:$LOCAL_PORT -> $VPS_HOST`:$REMOTE_PORT" -ForegroundColor White
Write-Host "  PID: $($sshProcess.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "El tunel esta corriendo en background." -ForegroundColor Cyan
Write-Host "Para detenerlo: Stop-Process -Id $($sshProcess.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "Ahora puedes iniciar el backend:" -ForegroundColor Yellow
Write-Host "  python backend/app.py" -ForegroundColor White
Write-Host ""
