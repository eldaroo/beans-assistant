#!/bin/bash
# Script para verificar el estado del servidor de WhatsApp

echo "=========================================="
echo "WhatsApp Server Status Check"
echo "=========================================="
echo ""

# Verificar si el proceso está corriendo
echo "[1] Checking if process is running..."
if pgrep -f "whatsapp_server.py" > /dev/null; then
    echo "✅ WhatsApp server is RUNNING"
    echo "   PID: $(pgrep -f whatsapp_server.py)"
else
    echo "❌ WhatsApp server is NOT running"
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
if [ -f "whatsapp.log" ]; then
    echo "--- whatsapp.log ---"
    tail -10 whatsapp.log
elif systemctl is-active --quiet whatsapp-bot 2>/dev/null; then
    echo "--- systemd journal ---"
    journalctl -u whatsapp-bot -n 10 --no-pager
else
    echo "ℹ️  No logs found"
fi
echo ""

echo "=========================================="
echo "Summary:"
echo "=========================================="

# Resumen
RUNNING=0
if pgrep -f "whatsapp_server.py" > /dev/null; then
    RUNNING=1
fi

if [ $RUNNING -eq 1 ]; then
    echo "✅ Server Status: RUNNING"
    echo ""
    echo "To view logs in real-time:"
    if screen -ls | grep -q "whatsapp"; then
        echo "  screen -r whatsapp"
    elif systemctl is-active --quiet whatsapp-bot 2>/dev/null; then
        echo "  sudo journalctl -u whatsapp-bot -f"
    else
        echo "  tail -f whatsapp.log"
    fi
    echo ""
    echo "To stop the server:"
    if screen -ls | grep -q "whatsapp"; then
        echo "  screen -r whatsapp"
        echo "  (then press Ctrl+C)"
    elif systemctl is-active --quiet whatsapp-bot 2>/dev/null; then
        echo "  sudo systemctl stop whatsapp-bot"
    else
        echo "  kill $(pgrep -f whatsapp_server.py)"
    fi
else
    echo "❌ Server Status: NOT RUNNING"
    echo ""
    echo "To start the server:"
    if [ -f "/etc/systemd/system/whatsapp-bot.service" ]; then
        echo "  sudo systemctl start whatsapp-bot"
    else
        echo "  screen -S whatsapp"
        echo "  source .venv/bin/activate"
        echo "  python whatsapp_server.py"
        echo "  (then press Ctrl+A, D to detach)"
    fi
fi

echo "=========================================="
