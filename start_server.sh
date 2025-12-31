#!/bin/bash
# Script de inicio rápido para el servidor de WhatsApp

echo "=========================================="
echo "Starting WhatsApp Server"
echo "=========================================="
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "whatsapp_server.py" ]; then
    echo "❌ Error: whatsapp_server.py not found"
    echo "   Make sure you're in the project directory"
    exit 1
fi

# Verificar .env
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found"
    echo "   Please create .env with your credentials"
    exit 1
fi

# Verificar entorno virtual
if [ ! -d ".venv" ]; then
    echo "⚠️  Virtual environment not found. Creating..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "✅ Environment activated"
echo ""

# Verificar si ya está corriendo
if pgrep -f "whatsapp_server.py" > /dev/null; then
    echo "⚠️  Server is already running!"
    echo "   PID: $(pgrep -f whatsapp_server.py)"
    echo ""
    echo "Options:"
    echo "  1. Stop it first: kill $(pgrep -f whatsapp_server.py)"
    echo "  2. View logs: ./check_server.sh"
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
    nohup python whatsapp_server.py > whatsapp.log 2>&1 &
    sleep 2
    echo ""
    echo "✅ Server started in background (nohup)"
    echo "   PID: $!"
    echo ""
    echo "Commands:"
    echo "  View logs:    tail -f whatsapp.log"
    echo "  Stop server:  kill $(pgrep -f whatsapp_server.py)"
    exit 0
fi

# Iniciar con screen
echo "🖥️  Starting with screen..."
echo ""
echo "Creating screen session 'whatsapp'..."

screen -dmS whatsapp bash -c "source .venv/bin/activate && python whatsapp_server.py"

sleep 2

if screen -ls | grep -q "whatsapp"; then
    echo "✅ Server started in screen session"
    echo ""
    echo "Commands:"
    echo "  View logs:       screen -r whatsapp"
    echo "  Detach:          Press Ctrl+A, then D"
    echo "  Stop server:     screen -r whatsapp, then Ctrl+C"
    echo "  Check status:    ./check_server.sh"
    echo ""
    echo "Tip: To view logs now, run: screen -r whatsapp"
else
    echo "❌ Failed to start screen session"
    exit 1
fi

echo "=========================================="
