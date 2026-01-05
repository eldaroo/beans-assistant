#!/bin/bash
# Script de deployment para servidor multi-tenant

echo "============================================================"
echo "Deployment Multi-Tenant Server"
echo "============================================================"

# 1. Stop current server
echo ""
echo "[1/5] Stopping current server..."
./stop_server.sh

# 2. Backup current database
echo ""
echo "[2/5] Creating backup..."
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

if [ -f "beansco.db" ]; then
    cp beansco.db "$BACKUP_DIR/beansco.db"
    echo "[OK] Database backed up to: $BACKUP_DIR"
fi

# 3. Setup client 1 with correct phone number
echo ""
echo "[3/5] Setting up Client 1..."
python3 setup_client1.py --force

# 4. Update start script to use multi-tenant server
echo ""
echo "[4/5] Updating start script..."

# Check if start_server.sh uses old server
if grep -q "whatsapp_server.py" start_server.sh; then
    echo "[!] Updating start_server.sh to use whatsapp_server_multitenant.py"

    # Backup original
    cp start_server.sh start_server.sh.backup

    # Replace
    sed -i 's/python whatsapp_server.py/python whatsapp_server_multitenant.py/g' start_server.sh
    sed -i 's/python3 whatsapp_server.py/python3 whatsapp_server_multitenant.py/g' start_server.sh

    echo "[OK] start_server.sh updated"
else
    echo "[OK] start_server.sh already uses multi-tenant server"
fi

# 5. Start multi-tenant server
echo ""
echo "[5/5] Starting multi-tenant server..."
./start_server.sh

echo ""
echo "============================================================"
echo "[OK] Deployment complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Check server logs: sudo journalctl -u whatsapp-bot -f"
echo "   OR: tail -f whatsapp.log"
echo "2. Send test message from +5491153695627"
echo "3. Verify it recognizes you as existing client"
echo ""
echo "Backup location: $BACKUP_DIR"
echo "============================================================"
