#!/bin/bash
# Script para iniciar WhatsApp Connector (Baileys) en el VPS
# El backend NO corre en el VPS, solo en local (Windows)

echo "=========================================="
echo "Starting WhatsApp Connector (Baileys)"
echo "=========================================="
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "whatsapp_baileys/server.js" ]; then
    echo "❌ Error: whatsapp_baileys/server.js not found"
    echo "   Make sure you're in the project directory"
    exit 1
fi

# Verificar .env
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found"
    echo "   Please create .env with your credentials"
    exit 1
fi

# Verificar Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    echo "   Install Node.js 20+ to run Baileys connector"
    exit 1
fi

# Instalar dependencias de Baileys si faltan
if [ ! -d "whatsapp_baileys/node_modules" ]; then
    echo "📦 Installing Baileys dependencies..."
    (cd whatsapp_baileys && npm install --omit=dev) || exit 1
    echo "✅ Dependencies installed"
fi

echo ""

# Verificar si ya está corriendo
WHATSAPP_RUNNING=$(pgrep -f "whatsapp_baileys/server.js")

if [ -n "$WHATSAPP_RUNNING" ]; then
    echo "⚠️  WhatsApp connector already running (PID: $WHATSAPP_RUNNING)"
    echo ""
    echo "Options:"
    echo "  1. Stop it:       ./stop_server.sh"
    echo "  2. View logs:     screen -r whatsapp"
    echo "  3. Check status:  ./check_server.sh"
    exit 1
fi

# Verificar si existe servicio systemd
if [ -f "/etc/systemd/system/whatsapp-bot.service" ]; then
    echo "🔧 Systemd service detected"
    echo "   Starting with systemd..."
    sudo systemctl start whatsapp-bot
    sleep 2
    sudo systemctl status whatsapp-bot --no-pager
    echo ""
    echo "✅ Server started with systemd"
    echo ""
    echo "Commands:"
    echo "  View logs:    sudo journalctl -u whatsapp-bot -f"
    echo "  Stop server:  sudo systemctl stop whatsapp-bot"
    echo "  Restart:      sudo systemctl restart whatsapp-bot"
    exit 0
fi

# Verificar si screen está instalado
if ! command -v screen &> /dev/null; then
    echo "⚠️  'screen' is not installed"
    echo "   Starting with nohup instead..."

    # Start WhatsApp connector
    echo "Starting WhatsApp Connector..."
    nohup node whatsapp_baileys/server.js > whatsapp.log 2>&1 &
    WHATSAPP_PID=$!
    sleep 2

    echo ""
    echo "✅ WhatsApp connector started in background (nohup)"
    echo "   PID: $WHATSAPP_PID"
    echo ""
    echo "Commands:"
    echo "  View logs:  tail -f whatsapp.log"
    echo "  Stop:       kill $WHATSAPP_PID"
    exit 0
fi

# Iniciar con screen
echo "🖥️  Starting with screen..."
echo ""

# Detener sesión anterior si existe
screen -S whatsapp -X quit 2>/dev/null

# Start WhatsApp in screen
echo "Creating screen session 'whatsapp'..."
screen -dmS whatsapp bash -c "node whatsapp_baileys/server.js"
sleep 2

# Check if running
WHATSAPP_OK=$(screen -ls | grep -c "whatsapp")

if [ "$WHATSAPP_OK" -gt 0 ]; then
    echo "✅ WhatsApp connector started in screen session 'whatsapp'"
    echo ""
    echo "Commands:"
    echo "  View logs:    screen -r whatsapp"
    echo "  Detach:       Ctrl+A, then D"
    echo "  Stop server:  ./stop_server.sh"
    echo "  Check status: ./check_server.sh"
    echo ""
    echo "Tip: To view logs now, run: screen -r whatsapp"
else
    echo "❌ Failed to start WhatsApp screen session"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ WhatsApp Connector started!"
echo "=========================================="
echo ""
echo "Note: Backend API runs on local machine (Windows), not on VPS"
