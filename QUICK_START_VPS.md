# 🚀 Quick Start - VPS

Comandos rápidos para correr el bot en tu VPS.

## ⚡ Setup Rápido (Primera vez)

```bash
# 1. Instalar dependencias del sistema
sudo apt update && sudo apt install -y python3 python3-pip python3-venv screen

# 2. Crear entorno virtual
python3 -m venv .venv

# 3. Activar entorno virtual
source .venv/bin/activate

# 4. Instalar dependencias de Python
pip install -r requirements.txt

# 5. Configurar .env (edita con tus credenciales)
nano .env

# 6. Iniciar el servidor
./start_server.sh
```

## 🎮 Comandos Principales

### ✅ Iniciar el servidor
```bash
./start_server.sh
```

### 🛑 Detener el servidor
```bash
./stop_server.sh
```

### 🔍 Ver estado
```bash
./check_server.sh
```

### 📋 Ver logs en tiempo real
```bash
# Con screen (método por defecto)
screen -r whatsapp

# Con systemd
sudo journalctl -u whatsapp-bot -f

# Con nohup
tail -f whatsapp.log
```

## 🔄 Actualizar desde Git

```bash
# 1. Detener servidor
./stop_server.sh

# 2. Obtener cambios
git pull

# 3. Activar entorno virtual
source .venv/bin/activate

# 4. Actualizar dependencias
pip install -r requirements.txt

# 5. Reiniciar servidor
./start_server.sh
```

## 🧪 Probar que funciona

```bash
# 1. Verificar estado
./check_server.sh

# 2. Probar conexión con Green API
source .venv/bin/activate
python check_account.py

# 3. Enviar un mensaje de WhatsApp
# Envía: "cuántas pulseras tengo?"
# Deberías recibir respuesta
```

## 📱 Monitoreo

### Ver logs en vivo
```bash
screen -r whatsapp
# Para salir sin detener: Ctrl+A, luego D
```

### Ver últimos errores
```bash
tail -50 whatsapp.log | grep -i error
```

### Ver procesos activos
```bash
ps aux | grep python
```

## 🆘 Troubleshooting Rápido

### El bot no responde
```bash
# 1. Verificar que está corriendo
./check_server.sh

# 2. Ver logs
screen -r whatsapp

# 3. Reiniciar
./stop_server.sh
./start_server.sh
```

### Error "Module not found"
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Problemas con Green API
```bash
source .venv/bin/activate
python test_whatsapp.py
```

## 📖 Documentación Completa

Para instrucciones detalladas, ver: **[VPS_DEPLOYMENT.md](VPS_DEPLOYMENT.md)**

## 🔐 Seguridad

```bash
# Proteger archivo .env
chmod 600 .env

# Verificar que .env no está en git
git status
# No debería aparecer .env
```

## 💡 Tips

1. **Usa screen** para mantener el servidor corriendo después de cerrar SSH
2. **Monitorea los logs** regularmente con `./check_server.sh`
3. **Haz backups** de `beansco.db` regularmente
4. Para **producción**: usa systemd (ver [VPS_DEPLOYMENT.md](VPS_DEPLOYMENT.md#opción-3-usando-systemd-producción---más-robusto))

## ✅ Checklist Post-Deployment

- [ ] Servidor corriendo: `./check_server.sh`
- [ ] Green API autorizada: `python check_account.py`
- [ ] Mensaje de prueba enviado y respondido
- [ ] Logs visibles: `screen -r whatsapp`
- [ ] .env protegido: `ls -la .env` (debería mostrar -rw-------)

---

**¿Problemas?** Consulta la [Guía Completa de Deployment](VPS_DEPLOYMENT.md)
