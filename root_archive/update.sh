#!/bin/bash
# Script para actualizar el servidor desde Git

echo "=========================================="
echo "🔄 Updating Server from Git"
echo "=========================================="
echo ""

# Verificar que estamos en un repositorio git
if [ ! -d ".git" ]; then
    echo "❌ Error: Not a git repository"
    echo "   Make sure you're in the project directory"
    exit 1
fi

# Verificar que hay cambios remotos
echo "📡 Checking for updates..."
git fetch

LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u})

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "✅ Already up to date (no changes)"
    echo ""
    echo "Do you want to restart the server anyway? (y/n)"
    read -r response
    if [ "$response" != "y" ]; then
        exit 0
    fi
else
    echo "📥 Updates available!"
    echo ""

    # Mostrar cambios que se van a aplicar
    echo "Changes to be pulled:"
    echo "---"
    git log HEAD..@{u} --oneline --decorate
    echo "---"
    echo ""
fi

# Paso 1: Detener el servidor
echo "[1/5] 🛑 Stopping server..."
./stop_server.sh
sleep 2
echo "✅ Server stopped"
echo ""

# Paso 2: Hacer backup de archivos importantes
echo "[2/5] 💾 Creating backup..."
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

if [ -f "beansco.db" ]; then
    cp beansco.db "$BACKUP_DIR/beansco.db"
    echo "✅ Database backed up to $BACKUP_DIR/beansco.db"
fi

if [ -f ".env" ]; then
    cp .env "$BACKUP_DIR/.env"
    echo "✅ .env backed up to $BACKUP_DIR/.env"
fi
echo ""

# Paso 3: Obtener cambios de Git
echo "[3/5] 📥 Pulling changes from Git..."

# Guardar cambios locales si los hay (por si acaso)
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  Local changes detected, stashing..."
    git stash
    STASHED=1
else
    STASHED=0
fi

# Hacer pull
if git pull; then
    echo "✅ Changes pulled successfully"
else
    echo "❌ Failed to pull changes"
    echo "   Please resolve conflicts manually"
    exit 1
fi

# Restaurar cambios locales si los había
if [ $STASHED -eq 1 ]; then
    echo "⚠️  Restoring local changes..."
    if git stash pop; then
        echo "✅ Local changes restored"
    else
        echo "⚠️  Conflicts detected, please resolve manually"
    fi
fi
echo ""

# Paso 4: Actualizar dependencias
echo "[4/5] 📦 Updating dependencies..."

# Python dependencies (backend)
if [ -d ".venv" ]; then
    source .venv/bin/activate
    if git diff HEAD@{1} HEAD --name-only | grep -q "requirements.txt"; then
        echo "⚠️  requirements.txt changed, updating Python packages..."
        pip install -r requirements.txt --upgrade
        echo "✅ Python dependencies updated"
    else
        echo "ℹ️  requirements.txt unchanged, skipping Python update"
    fi
else
    echo "ℹ️  .venv not found, skipping Python dependencies on VPS script"
fi

# Node dependencies (Baileys connector)
if [ -f "whatsapp_baileys/package.json" ]; then
    if [ ! -d "whatsapp_baileys/node_modules" ] || git diff HEAD@{1} HEAD --name-only | grep -q "whatsapp_baileys/package.json"; then
        echo "⚠️  Installing Node dependencies for Baileys..."
        (cd whatsapp_baileys && npm install --omit=dev)
        echo "✅ Node dependencies updated"
    else
        echo "ℹ️  Node dependencies unchanged, skipping"
    fi
fi
echo ""

# Paso 5: Reiniciar el servidor
echo "[5/5] 🚀 Restarting server..."
./start_server.sh
sleep 3
echo ""

# Verificar que el servidor está corriendo
echo "=========================================="
echo "🔍 Verification"
echo "=========================================="
echo ""

if pgrep -f "whatsapp_baileys/server.js" > /dev/null; then
    echo "✅ Server is running!"
    echo "   PID: $(pgrep -f whatsapp_baileys/server.js)"
    echo ""
    echo "Commands:"
    echo "  View status: ./check_server.sh"
    echo "  View logs:   screen -r whatsapp"
else
    echo "❌ Server failed to start"
    echo "   Check logs for errors"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ Update Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Server stopped"
echo "  - Backup created: $BACKUP_DIR"
echo "  - Changes pulled from Git"
echo "  - Dependencies updated (if needed)"
echo "  - Server restarted"
echo ""
echo "Next steps:"
echo "  1. Test with a WhatsApp message"
echo "  2. Monitor logs: screen -r whatsapp"
echo ""
