#!/bin/bash
# Script para detener el servidor de WhatsApp

echo "=========================================="
echo "Stopping WhatsApp Server"
echo "=========================================="
echo ""

# Verificar si está corriendo
if ! pgrep -f "whatsapp_server.py" > /dev/null; then
    echo "ℹ️  Server is not running"
    exit 0
fi

PID=$(pgrep -f whatsapp_server.py)
echo "Found process: PID $PID"
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
if screen -ls | grep -q "whatsapp"; then
    echo "🖥️  Killing screen session 'whatsapp'..."
    screen -X -S whatsapp quit
    sleep 1

    if screen -ls | grep -q "whatsapp"; then
        echo "⚠️  Screen session still exists, force killing process..."
        kill $PID
    else
        echo "✅ Screen session stopped"
    fi
else
    # Matar proceso directamente
    echo "🔪 Killing process $PID..."
    kill $PID
    sleep 1
fi

# Verificar que se detuvo
if pgrep -f "whatsapp_server.py" > /dev/null; then
    echo "⚠️  Process still running, force killing..."
    kill -9 $(pgrep -f whatsapp_server.py)
    sleep 1

    if pgrep -f "whatsapp_server.py" > /dev/null; then
        echo "❌ Failed to stop server"
        exit 1
    fi
fi

echo "✅ Server stopped successfully"
echo "=========================================="
