# Guía de Deployment en VPS

Guía completa para ejecutar el asistente de WhatsApp en un servidor VPS.

## 📋 Requisitos Previos

- VPS con Ubuntu/Debian (o similar)
- Python 3.9 o superior
- Acceso SSH al servidor
- Repositorio clonado en el VPS

## 🚀 Setup Inicial (Primera vez)

### 1. Conéctate al VPS

```bash
ssh usuario@tu-servidor.com
```

### 2. Navega al directorio del proyecto

```bash
cd /ruta/a/supabase-sql-agent
```

### 3. Instala Python y dependencias del sistema

```bash
# Actualizar paquetes
sudo apt update && sudo apt upgrade -y

# Instalar Python y herramientas
sudo apt install python3 python3-pip python3-venv -y

# Instalar screen o tmux (para mantener procesos corriendo)
sudo apt install screen -y
```

### 4. Crea el entorno virtual

```bash
# Crear entorno virtual
python3 -m venv .venv

# Activar entorno virtual
source .venv/bin/activate

# Actualizar pip
pip install --upgrade pip
```

### 5. Instala las dependencias del proyecto

```bash
pip install -r requirements.txt
```

### 6. Configura el archivo .env

```bash
# Copia el ejemplo
cp .env.example .env

# Edita el archivo con tus credenciales
nano .env
```

Asegúrate de tener:
```bash
# Gemini
GOOGLE_API_KEY=tu-api-key-aqui
GEMINI_MODEL=gemini-2.0-flash-exp
GEMINI_TEMPERATURE=0.2

# Database
SQLITE_PATH=beansco.db

# Green API WhatsApp
GREEN_API_INSTANCE_ID=tu-instance-id
GREEN_API_TOKEN=tu-api-token
```

Guarda con `Ctrl+O`, Enter, y sal con `Ctrl+X`.

### 7. Verifica que la base de datos existe

```bash
ls -la beansco.db
```

Si no existe, asegúrate de tener una copia o inicializa la base de datos.

## 🏃 Ejecutar la Aplicación

### Opción 1: Usando Screen (Recomendado para empezar)

Screen te permite mantener procesos corriendo incluso después de cerrar SSH.

```bash
# Crear una nueva sesión de screen llamada "whatsapp"
screen -S whatsapp

# Activar el entorno virtual (si no está activado)
source .venv/bin/activate

# Ejecutar el servidor
python whatsapp_server.py
```

**Para salir de screen sin detener el proceso:**
- Presiona `Ctrl+A`, luego presiona `D` (detach)

**Para volver a conectarte a la sesión:**
```bash
screen -r whatsapp
```

**Para ver todas las sesiones de screen:**
```bash
screen -ls
```

**Para detener el servidor:**
- Reconecta a la sesión: `screen -r whatsapp`
- Presiona `Ctrl+C`
- Escribe `exit` para cerrar la sesión

### Opción 2: Usando nohup (Más simple)

```bash
# Activar entorno virtual
source .venv/bin/activate

# Ejecutar en segundo plano
nohup python whatsapp_server.py > whatsapp.log 2>&1 &

# El proceso ahora corre en segundo plano
# Los logs se guardan en whatsapp.log
```

**Para detener el servidor:**
```bash
# Encuentra el proceso
ps aux | grep whatsapp_server.py

# Mata el proceso (reemplaza PID con el número que veas)
kill PID
```

**Para ver los logs:**
```bash
tail -f whatsapp.log
```

### Opción 3: Usando systemd (Producción - Más robusto)

Crea un servicio de systemd para que se reinicie automáticamente.

```bash
# Crear el archivo de servicio
sudo nano /etc/systemd/system/whatsapp-bot.service
```

Pega este contenido (ajusta las rutas):
```ini
[Unit]
Description=WhatsApp Business Bot
After=network.target

[Service]
Type=simple
User=tu-usuario
WorkingDirectory=/ruta/completa/a/supabase-sql-agent
Environment="PATH=/ruta/completa/a/supabase-sql-agent/.venv/bin"
ExecStart=/ruta/completa/a/supabase-sql-agent/.venv/bin/python whatsapp_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Ejemplo con rutas reales:**
```ini
[Unit]
Description=WhatsApp Business Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/supabase-sql-agent
Environment="PATH=/home/ubuntu/supabase-sql-agent/.venv/bin"
ExecStart=/home/ubuntu/supabase-sql-agent/.venv/bin/python whatsapp_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Guarda y cierra (`Ctrl+O`, Enter, `Ctrl+X`).

**Activar y ejecutar el servicio:**
```bash
# Recargar configuración de systemd
sudo systemctl daemon-reload

# Habilitar el servicio para que inicie al arrancar
sudo systemctl enable whatsapp-bot

# Iniciar el servicio
sudo systemctl start whatsapp-bot

# Ver estado
sudo systemctl status whatsapp-bot

# Ver logs en tiempo real
sudo journalctl -u whatsapp-bot -f
```

**Comandos útiles:**
```bash
# Detener el servicio
sudo systemctl stop whatsapp-bot

# Reiniciar el servicio
sudo systemctl restart whatsapp-bot

# Deshabilitar auto-inicio
sudo systemctl disable whatsapp-bot

# Ver logs completos
sudo journalctl -u whatsapp-bot --no-pager
```

## 🔍 Verificar que está Funcionando

### 1. Verificar el proceso

**Si usas screen:**
```bash
screen -ls
# Deberías ver: whatsapp (Attached/Detached)
```

**Si usas nohup:**
```bash
ps aux | grep whatsapp_server.py
# Deberías ver el proceso corriendo
```

**Si usas systemd:**
```bash
sudo systemctl status whatsapp-bot
# Deberías ver: Active: active (running)
```

### 2. Verificar los logs

**Con screen:**
```bash
screen -r whatsapp
# Verás la salida del servidor
# Ctrl+A, D para salir
```

**Con nohup:**
```bash
tail -f whatsapp.log
# Ctrl+C para salir
```

**Con systemd:**
```bash
sudo journalctl -u whatsapp-bot -f
# Ctrl+C para salir
```

### 3. Probar enviando un mensaje

Envía un mensaje de WhatsApp a tu instancia:
```
cuántas pulseras tengo?
```

Deberías:
1. Ver el mensaje en los logs
2. Recibir una respuesta del bot

### 4. Verificar la instancia de Green API

```bash
source .venv/bin/activate
python check_account.py
```

Deberías ver:
```
Instance state: authorized
✅ Instance is authorized and ready!
```

## 🔄 Actualizar la Aplicación

Cuando hagas cambios y quieras actualizar el VPS:

```bash
# 1. Conectar al VPS
ssh usuario@tu-servidor.com

# 2. Ir al directorio
cd /ruta/a/supabase-sql-agent

# 3. Hacer pull de los cambios
git pull origin master

# 4. Activar entorno virtual
source .venv/bin/activate

# 5. Actualizar dependencias (si cambiaron)
pip install -r requirements.txt

# 6. Reiniciar el servidor
# Con screen:
screen -r whatsapp
# Ctrl+C para detener
# python whatsapp_server.py para reiniciar
# Ctrl+A, D para salir

# Con systemd:
sudo systemctl restart whatsapp-bot
```

## 🛠️ Troubleshooting

### El bot no responde a mensajes

```bash
# 1. Verifica que el proceso esté corriendo
ps aux | grep whatsapp

# 2. Revisa los logs para errores
tail -50 whatsapp.log

# 3. Verifica la conexión con Green API
python check_account.py

# 4. Prueba manualmente
python test_whatsapp.py
```

### Error "Module not found"

```bash
# Asegúrate de estar en el entorno virtual
source .venv/bin/activate

# Reinstala dependencias
pip install -r requirements.txt
```

### Error con la base de datos

```bash
# Verifica que existe
ls -la beansco.db

# Verifica permisos
chmod 644 beansco.db
```

### El proceso se detiene inesperadamente

**Con systemd (se reinicia automáticamente):**
```bash
sudo journalctl -u whatsapp-bot --since "1 hour ago"
# Revisa los logs para ver por qué se detuvo
```

**Con screen/nohup:**
```bash
# Usa systemd en su lugar para auto-reinicio
```

## 📊 Monitoreo

### Ver logs en tiempo real

```bash
# Con systemd
sudo journalctl -u whatsapp-bot -f

# Con nohup
tail -f whatsapp.log

# Con screen
screen -r whatsapp
```

### Verificar uso de recursos

```bash
# Ver uso de CPU y memoria
htop

# Ver procesos de Python
ps aux | grep python
```

### Verificar conectividad

```bash
# Ping a Green API
ping 7105.api.greenapi.com

# Verificar DNS
nslookup 7105.api.greenapi.com
```

## 🔐 Seguridad

1. **No expongas el .env:**
   ```bash
   chmod 600 .env
   ```

2. **Mantén el sistema actualizado:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

3. **Configura un firewall:**
   ```bash
   sudo ufw allow OpenSSH
   sudo ufw enable
   ```

4. **Usa claves SSH en lugar de contraseñas**

## 📝 Comandos Rápidos

```bash
# Iniciar (con screen)
screen -S whatsapp
source .venv/bin/activate
python whatsapp_server.py
# Ctrl+A, D

# Ver logs
screen -r whatsapp

# Detener
screen -r whatsapp
# Ctrl+C
exit

# Reiniciar (con systemd)
sudo systemctl restart whatsapp-bot

# Ver estado
sudo systemctl status whatsapp-bot
```

## ✅ Checklist de Deployment

- [ ] Python 3.9+ instalado
- [ ] Repositorio clonado
- [ ] Entorno virtual creado
- [ ] Dependencias instaladas
- [ ] Archivo .env configurado
- [ ] Base de datos presente
- [ ] Green API autorizada
- [ ] Servidor corriendo
- [ ] Mensajes de prueba funcionan
- [ ] Logs monitoreables
- [ ] Auto-reinicio configurado (systemd)

## 🎯 Recomendación

Para producción, usa **systemd** (Opción 3) porque:
- ✅ Se reinicia automáticamente si falla
- ✅ Inicia al arrancar el servidor
- ✅ Logs centralizados con journalctl
- ✅ Fácil de monitorear y gestionar
- ✅ Estándar en Linux

Para desarrollo/testing rápido, usa **screen** (Opción 1).
