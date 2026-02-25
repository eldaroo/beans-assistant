#!/bin/bash
# PostgreSQL SSH Tunnel Script
#
# Este script crea un túnel SSH seguro para conectar tu aplicación local
# al PostgreSQL en el VPS sin exponer el puerto a internet.
#
# Uso:
#   bash connect_db_tunnel.sh
#
# Para ejecutar en segundo plano:
#   bash connect_db_tunnel.sh &

echo "================================================"
echo "PostgreSQL SSH Tunnel"
echo "================================================"
echo ""

# Configuración (edita estos valores)
VPS_USER="root"             # Tu usuario SSH en el VPS
VPS_HOST="31.97.100.1"      # IP o dominio de tu VPS
VPS_PORT="22"               # Puerto SSH (normalmente 22)
LOCAL_PORT="5432"           # Puerto local para el túnel
REMOTE_PORT="5432"          # Puerto de PostgreSQL en el VPS

echo "Configuración:"
echo "  VPS: $VPS_USER@$VPS_HOST:$VPS_PORT"
echo "  Túnel: localhost:$LOCAL_PORT -> $VPS_HOST:$REMOTE_PORT"
echo ""

# Verificar si ya hay un túnel activo
if pgrep -f "ssh -L $LOCAL_PORT:localhost:$REMOTE_PORT" > /dev/null; then
    echo "⚠️  Ya hay un túnel SSH activo para el puerto $LOCAL_PORT"
    echo ""
    echo "Para cerrar el túnel existente, ejecuta:"
    echo "  pkill -f 'ssh -L $LOCAL_PORT'"
    echo ""
    exit 1
fi

# Verificar que el puerto local está libre
if lsof -Pi :$LOCAL_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "❌ El puerto $LOCAL_PORT ya está en uso"
    echo ""
    echo "Para ver qué proceso lo está usando:"
    echo "  lsof -i :$LOCAL_PORT"
    echo ""
    exit 1
fi

echo "🚀 Iniciando túnel SSH..."
echo ""
echo "Después de conectar:"
echo "  ✅ Tu backend local puede conectarse a PostgreSQL en localhost:$LOCAL_PORT"
echo "  ✅ Toda la comunicación está encriptada vía SSH"
echo "  ✅ No se expone ningún puerto al internet público"
echo ""
echo "Para detener el túnel: Ctrl+C (o ejecuta: pkill -f 'ssh -L $LOCAL_PORT')"
echo ""
echo "================================================"
echo ""

# Crear túnel SSH
# -L: Local port forwarding
# -N: No ejecutar comandos remotos (solo túnel)
# -v: Verbose (útil para debugging, puedes quitar -v en producción)
ssh -L $LOCAL_PORT:localhost:$REMOTE_PORT \
    -p $VPS_PORT \
    $VPS_USER@$VPS_HOST \
    -N

echo ""
echo "Túnel cerrado."
