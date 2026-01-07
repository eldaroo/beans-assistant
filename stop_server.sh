#!/bin/bash
# Script para detener los servidores (WhatsApp + Backend)

echo "=========================================="
echo "Stopping Servers"
echo "=========================================="
echo ""

# Verificar qué procesos están corriendo
WHATSAPP_PID=$(pgrep -f "whatsapp_server.py")
BACKEND_PID=$(pgrep -f "uvicorn backend.app:app")

if [ -z "$WHATSAPP_PID" ] && [ -z "$BACKEND_PID" ]; then
    echo "ℹ️  No servers are running"
    exit 0
fi

if [ -n "$WHATSAPP_PID" ]; then
    echo "Found WhatsApp server: PID $WHATSAPP_PID"
fi

if [ -n "$BACKEND_PID" ]; then
    echo "Found Backend API: PID $BACKEND_PID"
fi
echo ""

# Verificar si hay servicio systemd (solo para WhatsApp)
if systemctl is-active --quiet whatsapp-bot 2>/dev/null; then
    echo "🔧 Stopping systemd service..."
    sudo systemctl stop whatsapp-bot
    sleep 2

    if systemctl is-active --quiet whatsapp-bot 2>/dev/null; then
        echo "❌ Failed to stop systemd service"
        exit 1
    else
        echo "✅ Systemd service stopped"
        WHATSAPP_PID=""  # Clear PID as systemd handled it
    fi
fi

# Verificar si hay sesiones de screen
BACKEND_SCREEN=$(screen -ls | grep -c "backend")
WHATSAPP_SCREEN=$(screen -ls | grep -c "whatsapp")

if [ "$BACKEND_SCREEN" -gt 0 ]; then
    echo "🖥️  Killing screen session 'backend'..."
    screen -X -S backend quit
    sleep 1

    if screen -ls | grep -q "backend"; then
        echo "⚠️  Backend screen session still exists, force killing process..."
        [ -n "$BACKEND_PID" ] && kill $BACKEND_PID
    else
        echo "✅ Backend screen session stopped"
        BACKEND_PID=""  # Clear PID as screen handled it
    fi
fi

if [ "$WHATSAPP_SCREEN" -gt 0 ]; then
    echo "🖥️  Killing screen session 'whatsapp'..."
    screen -X -S whatsapp quit
    sleep 1

    if screen -ls | grep -q "whatsapp"; then
        echo "⚠️  WhatsApp screen session still exists, force killing process..."
        [ -n "$WHATSAPP_PID" ] && kill $WHATSAPP_PID
    else
        echo "✅ WhatsApp screen session stopped"
        WHATSAPP_PID=""  # Clear PID as screen handled it
    fi
fi

# Matar procesos directamente si aún existen
if [ -n "$BACKEND_PID" ]; then
    echo "🔪 Killing Backend process $BACKEND_PID..."
    kill $BACKEND_PID 2>/dev/null
    sleep 1
fi

if [ -n "$WHATSAPP_PID" ]; then
    echo "🔪 Killing WhatsApp process $WHATSAPP_PID..."
    kill $WHATSAPP_PID 2>/dev/null
    sleep 1
fi

# Verificar que se detuvieron y force kill si es necesario
FAILED=0

if pgrep -f "uvicorn backend.app:app" > /dev/null; then
    echo "⚠️  Backend still running, force killing..."
    kill -9 $(pgrep -f "uvicorn backend.app:app") 2>/dev/null
    sleep 1

    if pgrep -f "uvicorn backend.app:app" > /dev/null; then
        echo "❌ Failed to stop Backend"
        FAILED=1
    else
        echo "✅ Backend force killed"
    fi
fi

if pgrep -f "whatsapp_server.py" > /dev/null; then
    echo "⚠️  WhatsApp still running, force killing..."
    kill -9 $(pgrep -f whatsapp_server.py) 2>/dev/null
    sleep 1

    if pgrep -f "whatsapp_server.py" > /dev/null; then
        echo "❌ Failed to stop WhatsApp"
        FAILED=1
    else
        echo "✅ WhatsApp force killed"
    fi
fi

if [ $FAILED -eq 0 ]; then
    echo ""
    echo "✅ All servers stopped successfully"
fi

echo "=========================================="

exit $FAILED
