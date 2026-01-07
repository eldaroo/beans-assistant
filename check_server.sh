#!/bin/bash
# Script para verificar el estado de los servidores (WhatsApp + Backend)

echo "=========================================="
echo "Servers Status Check"
echo "=========================================="
echo ""

# Verificar si los procesos están corriendo
echo "[1] Checking if processes are running..."

# WhatsApp Server
if pgrep -f "whatsapp_server.py" > /dev/null; then
    echo "✅ WhatsApp server is RUNNING"
    echo "   PID: $(pgrep -f whatsapp_server.py)"
else
    echo "❌ WhatsApp server is NOT running"
fi

# Backend API
if pgrep -f "uvicorn backend.app:app" > /dev/null; then
    echo "✅ Backend API is RUNNING"
    echo "   PID: $(pgrep -f 'uvicorn backend.app:app')"
    echo "   URL: http://localhost:8000"
else
    echo "❌ Backend API is NOT running"
fi
echo ""

# Verificar sesiones de screen
echo "[2] Checking screen sessions..."

if screen -ls | grep -q "whatsapp"; then
    echo "✅ Screen session 'whatsapp' exists"
    screen -ls | grep whatsapp
else
    echo "ℹ️  No screen session named 'whatsapp'"
fi

if screen -ls | grep -q "backend"; then
    echo "✅ Screen session 'backend' exists"
    screen -ls | grep backend
else
    echo "ℹ️  No screen session named 'backend'"
fi
echo ""

# Verificar servicio systemd
echo "[3] Checking systemd service..."
if systemctl is-active --quiet whatsapp-bot 2>/dev/null; then
    echo "✅ Systemd service is ACTIVE"
    systemctl status whatsapp-bot --no-pager | head -10
else
    echo "ℹ️  Systemd service not found or not active"
fi
echo ""

# Verificar archivo .env
echo "[4] Checking .env file..."
if [ -f ".env" ]; then
    echo "✅ .env file exists"
    if grep -q "GREEN_API_INSTANCE_ID" .env && grep -q "GREEN_API_TOKEN" .env; then
        echo "✅ Green API credentials found in .env"
    else
        echo "⚠️  Green API credentials might be missing"
    fi
else
    echo "❌ .env file NOT found"
fi
echo ""

# Verificar base de datos
echo "[5] Checking database..."
if [ -f "beansco.db" ]; then
    echo "✅ Database file exists"
    echo "   Size: $(du -h beansco.db | cut -f1)"
else
    echo "❌ Database file NOT found"
fi
echo ""

# Verificar entorno virtual
echo "[6] Checking virtual environment..."
if [ -d ".venv" ]; then
    echo "✅ Virtual environment exists"
else
    echo "❌ Virtual environment NOT found"
fi
echo ""

# Verificar logs recientes
echo "[7] Recent logs (last 10 lines)..."

echo "--- WhatsApp Logs ---"
if [ -f "whatsapp.log" ]; then
    tail -10 whatsapp.log
elif systemctl is-active --quiet whatsapp-bot 2>/dev/null; then
    journalctl -u whatsapp-bot -n 10 --no-pager
else
    echo "ℹ️  No logs found"
fi

echo ""
echo "--- Backend Logs ---"
if [ -f "backend.log" ]; then
    tail -10 backend.log
else
    echo "ℹ️  No logs found"
fi
echo ""

echo "=========================================="
echo "Summary:"
echo "=========================================="

# Resumen
WHATSAPP_RUNNING=0
BACKEND_RUNNING=0

if pgrep -f "whatsapp_server.py" > /dev/null; then
    WHATSAPP_RUNNING=1
fi

if pgrep -f "uvicorn backend.app:app" > /dev/null; then
    BACKEND_RUNNING=1
fi

# WhatsApp Status
if [ $WHATSAPP_RUNNING -eq 1 ]; then
    echo "✅ WhatsApp Server: RUNNING"
else
    echo "❌ WhatsApp Server: NOT RUNNING"
fi

# Backend Status
if [ $BACKEND_RUNNING -eq 1 ]; then
    echo "✅ Backend API: RUNNING (http://localhost:8000)"
else
    echo "❌ Backend API: NOT RUNNING"
fi

echo ""
echo "Commands:"
echo ""

if [ $WHATSAPP_RUNNING -eq 1 ] || [ $BACKEND_RUNNING -eq 1 ]; then
    echo "To view logs in real-time:"
    if screen -ls | grep -q "whatsapp"; then
        echo "  WhatsApp: screen -r whatsapp"
    else
        echo "  WhatsApp: tail -f whatsapp.log"
    fi
    if screen -ls | grep -q "backend"; then
        echo "  Backend:  screen -r backend"
    else
        echo "  Backend:  tail -f backend.log"
    fi
    echo ""
    echo "To stop servers:"
    if screen -ls | grep -q "whatsapp\|backend"; then
        echo "  screen -X -S backend quit && screen -X -S whatsapp quit"
    else
        echo "  kill $(pgrep -f 'whatsapp_server.py\|uvicorn backend.app:app')"
    fi
else
    echo "To start servers:"
    echo "  ./start_server.sh"
fi

echo "=========================================="
