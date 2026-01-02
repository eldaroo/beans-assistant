#!/bin/bash
# Script to initialize the database on the server

echo "=========================================="
echo "🗄️  Database Setup"
echo "=========================================="
echo ""

DB_FILE="beansco.db"
BACKUP_DIR="backups/db_backups"

# Check if database already exists
if [ -f "$DB_FILE" ]; then
    echo "⚠️  Database file already exists: $DB_FILE"
    echo ""

    # Check if it has tables
    TABLES=$(sqlite3 $DB_FILE ".tables" 2>/dev/null)

    if [ -n "$TABLES" ]; then
        echo "📊 Existing tables found:"
        echo "$TABLES"
        echo ""
        echo "Options:"
        echo "  1. Keep existing database (recommended if you have data)"
        echo "  2. Backup and recreate (WARNING: will backup old and create new)"
        echo "  3. Cancel"
        echo ""
        read -p "Choose option (1/2/3): " choice

        case $choice in
            1)
                echo "✅ Keeping existing database"
                exit 0
                ;;
            2)
                # Create backup
                mkdir -p "$BACKUP_DIR"
                BACKUP_FILE="$BACKUP_DIR/beansco.db.backup.$(date +%Y%m%d_%H%M%S)"
                echo "💾 Creating backup: $BACKUP_FILE"
                cp "$DB_FILE" "$BACKUP_FILE"
                echo "✅ Backup created"

                # Remove old database
                rm "$DB_FILE"
                echo "🗑️  Old database removed"
                ;;
            3)
                echo "❌ Cancelled"
                exit 0
                ;;
            *)
                echo "❌ Invalid option"
                exit 1
                ;;
        esac
    else
        echo "ℹ️  Database file exists but has no tables"
    fi
fi

# Check if init_database.sql exists
if [ ! -f "init_database.sql" ]; then
    echo "❌ Error: init_database.sql not found"
    echo "   Make sure you ran 'git pull' first"
    exit 1
fi

# Check if sqlite3 is installed
if ! command -v sqlite3 &> /dev/null; then
    echo "❌ sqlite3 is not installed"
    echo "   Installing..."
    sudo apt update
    sudo apt install -y sqlite3
fi

# Create database and tables
echo "🔨 Creating database and tables..."
sqlite3 "$DB_FILE" < init_database.sql

if [ $? -eq 0 ]; then
    echo "✅ Database created successfully"
else
    echo "❌ Failed to create database"
    exit 1
fi

# Verify
echo ""
echo "🔍 Verification:"
echo "─────────────────────────────────────────"

echo ""
echo "Tables created:"
sqlite3 "$DB_FILE" ".tables"

echo ""
echo "Products:"
sqlite3 "$DB_FILE" "SELECT sku, name, unit_price_cents/100.0 as price_usd FROM products;"

echo ""
echo "Current stock:"
sqlite3 "$DB_FILE" "SELECT name, stock_qty FROM stock_current;"

echo ""
echo "─────────────────────────────────────────"
echo "✅ Database setup complete!"
echo ""
echo "Database file: $DB_FILE"
echo "Size: $(du -h $DB_FILE | cut -f1)"
echo ""
echo "Next steps:"
echo "  1. Start the server: ./start_server.sh"
echo "  2. Send a test message via WhatsApp"
echo "=========================================="
