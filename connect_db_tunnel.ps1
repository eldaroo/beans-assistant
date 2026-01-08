# PostgreSQL SSH Tunnel for Windows
# PowerShell script to create SSH tunnel to VPS PostgreSQL

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "PostgreSQL SSH Tunnel (Windows)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$VPS_USER = "root"
$VPS_HOST = "31.97.100.1"
$VPS_PORT = 22
$LOCAL_PORT = 5432
$REMOTE_PORT = 5432

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  VPS: $VPS_USER@$VPS_HOST`:$VPS_PORT"
Write-Host "  Tunnel: localhost:$LOCAL_PORT -> $VPS_HOST`:$REMOTE_PORT"
Write-Host ""

# Check if port is already in use
$portInUse = Get-NetTCPConnection -LocalPort $LOCAL_PORT -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "WARNING: Port $LOCAL_PORT is already in use!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check what's using it:" -ForegroundColor Yellow
    Write-Host "  Get-NetTCPConnection -LocalPort $LOCAL_PORT | Select-Object OwningProcess | Get-Process" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Press Ctrl+C to cancel or Enter to continue anyway..."
    Read-Host
}

Write-Host "Starting SSH tunnel..." -ForegroundColor Green
Write-Host ""
Write-Host "After connecting:" -ForegroundColor Yellow
Write-Host "  - Your backend can connect to PostgreSQL at localhost:$LOCAL_PORT"
Write-Host "  - All traffic is encrypted via SSH"
Write-Host "  - No public ports exposed"
Write-Host ""
Write-Host "To stop: Press Ctrl+C" -ForegroundColor Yellow
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Create SSH tunnel
# -L: Local port forwarding
# -N: Don't execute remote commands (tunnel only)
ssh -L ${LOCAL_PORT}:localhost:${REMOTE_PORT} -p $VPS_PORT ${VPS_USER}@${VPS_HOST} -N

Write-Host ""
Write-Host "Tunnel closed." -ForegroundColor Red
