# Script para iniciar entorno de desarrollo completo

Write-Host "🚀 Iniciando entorno de desarrollo" -ForegroundColor Cyan
Write-Host ""

# 1. Iniciar túnel SSH en ventana separada
Write-Host "1. Iniciando túnel SSH..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy Bypass", "-File `"$PSScriptRoot\keep_tunnel_alive.ps1`""

# Esperar a que el túnel se establezca
Write-Host "   Esperando conexión..." -ForegroundColor Gray
Start-Sleep -Seconds 3

# 2. Verificar conexión a PostgreSQL
Write-Host "2. Verificando conexión a PostgreSQL..." -ForegroundColor Yellow
try {
    $result = python -c "from database_config import db; print('OK' if db.fetch_one('SELECT 1') else 'FAIL')" 2>&1
    if ($result -like "*OK*") {
        Write-Host "   ✅ PostgreSQL conectado" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Error conectando a PostgreSQL" -ForegroundColor Red
        Write-Host "   $result" -ForegroundColor Gray
    }
} catch {
    Write-Host "   ⚠️  No se pudo verificar conexión" -ForegroundColor Yellow
}

# 3. Iniciar backend
Write-Host "3. Iniciando backend local..." -ForegroundColor Yellow
bash restart_backend.sh

Write-Host ""
Write-Host "✅ Entorno listo!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 API: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "🗄️  PostgreSQL: localhost:5433 (túnel SSH)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Para detener: cierra la ventana del túnel SSH" -ForegroundColor Yellow
