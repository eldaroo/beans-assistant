#!/bin/bash
# Script para detener WhatsApp Server en el VPS
# El backend NO corre en el VPS, solo en local (Windows)

echo "=========================================="
echo "Stopping WhatsApp Server"
echo "=========================================="
echo ""

# Verificar qué procesos están corriendo
WHATSAPP_PID=$(pgrep -f "whatsapp_server")

if [ -z "$WHATSAPP_PID" ]; then
    echo "ℹ️  WhatsApp server is not running"
    exit 0
fi

echo "Found WhatsApp server: PID $WHATSAPP_PID"
echo ""

# Verificar si hay servicio systemd
if systemctl is-active --quiet whatsapp-bot 2>/dev/null; then
    echo "🔧 Stopping systemd service..."
    sudo systemctl stop whatsapp-bot
    sleep 2

    if systemctl is-active --quiet whatsapp-bot 2>/dev/null; then
        echo "❌ Failed to stop systemd service"
        exit 1
    else
        echo "✅ Systemd service stopped"
        exit 0
    fi
fi

# Verificar si hay sesión de screen
WHATSAPP_SCREEN=$(screen -ls 2>/dev/null | grep -c "whatsapp")

if [ "$WHATSAPP_SCREEN" -gt 0 ]; then
    echo "🖥️  Killing screen session 'whatsapp'..."
    screen -X -S whatsapp quit
    sleep 1

    if screen -ls 2>/dev/null | grep -q "whatsapp"; then
        echo "⚠️  Screen session still exists, force killing process..."
        kill $WHATSAPP_PID 2>/dev/null
    else
        echo "✅ WhatsApp screen session stopped"
        WHATSAPP_PID=""  # Clear PID as screen handled it
    fi
fi

# Matar proceso directamente si aún existe
if [ -n "$WHATSAPP_PID" ]; then
    echo "🔪 Killing WhatsApp process $WHATSAPP_PID..."
    kill $WHATSAPP_PID 2>/dev/null
    sleep 1
fi

# Verificar que se detuvo y force kill si es necesario
if pgrep -f "whatsapp_server" > /dev/null; then
    echo "⚠️  WhatsApp still running, force killing..."
    kill -9 $(pgrep -f "whatsapp_server") 2>/dev/null
    sleep 1

    if pgrep -f "whatsapp_server" > /dev/null; then
        echo "❌ Failed to stop WhatsApp server"
        exit 1
    else
        echo "✅ WhatsApp force killed"
    fi
fi

echo ""
echo "✅ WhatsApp server stopped successfully"
echo ""
echo "=========================================="
echo ""
echo "Note: Backend API runs on local machine (Windows), not on VPS"

exit 0
