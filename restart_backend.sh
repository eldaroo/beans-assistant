#!/bin/bash
# Script para reiniciar el backend limpiamente

echo "=========================================="
echo "Restarting Backend Server"
echo "=========================================="
echo ""

# Matar todos los procesos Python
echo "Killing all Python processes..."
taskkill //F //IM python.exe //T 2>/dev/null

# Esperar un momento
sleep 2

# Limpiar cache de Python
echo "Cleaning Python cache..."
find backend -name "*.pyc" -delete 2>/dev/null
find backend -name "__pycache__" -type d -delete 2>/dev/null

# Iniciar servidor
echo "Starting backend server..."
python -m uvicorn backend.app:app --port 8000 --reload &

sleep 3

# Verificar que esté corriendo
echo ""
echo "Checking server status..."
curl -s http://localhost:8000/health | python -m json.tool

echo ""
echo "=========================================="
echo "✅ Backend server restarted!"
echo "   URL: http://localhost:8000"
echo "=========================================="
