# Script de diagnostico para verificar conectividad SSH y PostgreSQL

$VPS_USER = "root"
$VPS_HOST = "31.97.100.1"
$LOCAL_PORT = 5433
$REMOTE_PORT = 5432

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  DIAGNOSTICO SSH Y POSTGRESQL" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Test 1: Verificar conectividad basica al VPS
Write-Host "[1/5] Verificando conectividad al VPS..." -ForegroundColor Yellow
Write-Host "  Host: $VPS_HOST" -ForegroundColor Gray

try {
    $ping = Test-Connection -ComputerName $VPS_HOST -Count 2 -Quiet
    if ($ping) {
        Write-Host "  [OK] VPS es alcanzable" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] VPS no responde a ping" -ForegroundColor Red
        Write-Host "  Verifica la IP y tu conexion a internet" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [ERROR] No se pudo hacer ping al VPS" -ForegroundColor Red
}

# Test 2: Verificar acceso SSH
Write-Host ""
Write-Host "[2/5] Verificando acceso SSH..." -ForegroundColor Yellow
Write-Host "  Intentando conectar a $VPS_USER@$VPS_HOST" -ForegroundColor Gray

$sshTest = ssh -o ConnectTimeout=5 -o BatchMode=yes $VPS_USER@$VPS_HOST "echo OK" 2>&1
if ($sshTest -eq "OK") {
    Write-Host "  [OK] SSH funciona con keys (sin password)" -ForegroundColor Green
} else {
    Write-Host "  [WARNING] SSH requiere password o hay un problema" -ForegroundColor Yellow
    Write-Host "  Output: $sshTest" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Recomendacion: Configura SSH keys para evitar passwords" -ForegroundColor Yellow
    Write-Host "  1. En tu PC: ssh-keygen (si no tienes keys)" -ForegroundColor Gray
    Write-Host "  2. Copia la key: ssh-copy-id $VPS_USER@$VPS_HOST" -ForegroundColor Gray
}

# Test 3: Verificar PostgreSQL en el servidor remoto
Write-Host ""
Write-Host "[3/5] Verificando PostgreSQL en el servidor..." -ForegroundColor Yellow

$pgStatus = ssh -o ConnectTimeout=5 $VPS_USER@$VPS_HOST "systemctl is-active postgresql" 2>&1
if ($pgStatus -eq "active") {
    Write-Host "  [OK] PostgreSQL esta corriendo" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] PostgreSQL no esta activo" -ForegroundColor Red
    Write-Host "  Status: $pgStatus" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Para iniciar PostgreSQL en el servidor:" -ForegroundColor Yellow
    Write-Host "  ssh $VPS_USER@$VPS_HOST 'systemctl start postgresql'" -ForegroundColor Gray
}

# Test 4: Verificar que PostgreSQL escucha en el puerto correcto
Write-Host ""
Write-Host "[4/5] Verificando puerto PostgreSQL..." -ForegroundColor Yellow

$pgPort = ssh -o ConnectTimeout=5 $VPS_USER@$VPS_HOST "netstat -tlnp | grep :$REMOTE_PORT" 2>&1
if ($pgPort -match $REMOTE_PORT) {
    Write-Host "  [OK] PostgreSQL escucha en puerto $REMOTE_PORT" -ForegroundColor Green
} else {
    Write-Host "  [WARNING] PostgreSQL puede no estar escuchando en puerto $REMOTE_PORT" -ForegroundColor Yellow
    Write-Host "  Output: $pgPort" -ForegroundColor Gray
}

# Test 5: Verificar si ya hay un tunel activo
Write-Host ""
Write-Host "[5/5] Verificando tuneles SSH locales..." -ForegroundColor Yellow

$sshProcesses = Get-Process -Name ssh -ErrorAction SilentlyContinue
if ($sshProcesses) {
    Write-Host "  [INFO] Hay $($sshProcesses.Count) proceso(s) SSH corriendo:" -ForegroundColor Cyan
    $sshProcesses | ForEach-Object {
        Write-Host "    PID: $($_.Id)" -ForegroundColor Gray
    }
} else {
    Write-Host "  [INFO] No hay tuneles SSH activos" -ForegroundColor Gray
}

# Verificar si el puerto local esta en uso
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $tcpClient.Connect("127.0.0.1", $LOCAL_PORT)
    $tcpClient.Close()
    Write-Host "  [OK] Puerto $LOCAL_PORT esta respondiendo (tunel activo)" -ForegroundColor Green
} catch {
    Write-Host "  [INFO] Puerto $LOCAL_PORT no responde (tunel no activo)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  RESUMEN" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Siguiente paso:" -ForegroundColor Yellow
Write-Host "  Si todo esta OK arriba, ejecuta: .\setup_tunnel.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Si hay problemas:" -ForegroundColor Yellow
Write-Host "  1. Verifica que PostgreSQL este corriendo en el VPS" -ForegroundColor Gray
Write-Host "  2. Configura SSH keys para evitar passwords" -ForegroundColor Gray
Write-Host "  3. Verifica que el firewall permita SSH (puerto 22)" -ForegroundColor Gray
Write-Host ""
