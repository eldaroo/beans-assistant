# 🔄 Guía de Actualización del Servidor

Cómo actualizar el servidor en el VPS después de hacer cambios en tu código local.

## 🚀 Método Rápido (Recomendado)

### Desde tu computadora local:

```bash
# 1. Hacer commit de tus cambios
git add .
git commit -m "descripción de los cambios"

# 2. Pushear a GitHub/GitLab
git push origin master
```

### En el VPS:

```bash
# 1. Conectarte al VPS
ssh usuario@tu-vps.com

# 2. Ir al directorio del proyecto
cd /ruta/a/supabase-sql-agent

# 3. Ejecutar el script de actualización
./update.sh
```

**¡Listo!** El script automáticamente:
- ✅ Detiene el servidor
- ✅ Hace backup de la base de datos y .env
- ✅ Descarga los cambios de Git
- ✅ Actualiza dependencias (si cambiaron)
- ✅ Reinicia el servidor
- ✅ Verifica que todo funcione

---

## 🔧 Método Manual (Paso a Paso)

Si prefieres hacerlo manualmente o el script falla:

```bash
# 1. Conectarte al VPS
ssh usuario@tu-vps.com

# 2. Ir al directorio
cd /ruta/a/supabase-sql-agent

# 3. Detener el servidor
./stop_server.sh
# O manualmente:
# screen -r whatsapp
# Ctrl+C
# exit

# 4. Hacer backup (opcional pero recomendado)
cp beansco.db beansco.db.backup.$(date +%Y%m%d_%H%M%S)
cp .env .env.backup

# 5. Descargar cambios de Git
git pull origin master

# 6. Activar entorno virtual
source .venv/bin/activate

# 7. Actualizar dependencias (solo si requirements.txt cambió)
pip install -r requirements.txt --upgrade

# 8. Reiniciar servidor
./start_server.sh

# 9. Verificar que funciona
./check_server.sh
```

---

## 📋 Workflow Completo

### En tu máquina local:

```bash
# 1. Hacer cambios en el código
# ... editar archivos ...

# 2. Probar localmente (opcional)
source .venv/bin/activate
python test_whatsapp.py

# 3. Commit y push
git add .
git commit -m "Fix: corrección del bug de identificación de productos"
git push origin master
```

### En el VPS:

```bash
# Opción A: Script automático
./update.sh

# Opción B: Manual
./stop_server.sh
git pull
source .venv/bin/activate
pip install -r requirements.txt --upgrade
./start_server.sh
./check_server.sh
```

---

## 🆘 Troubleshooting

### Error: "Conflicts detected"

Si hay conflictos al hacer `git pull`:

```bash
# Ver qué archivos tienen conflictos
git status

# Opción 1: Descartar cambios locales (usar con cuidado)
git reset --hard origin/master

# Opción 2: Resolver conflictos manualmente
# Edita los archivos con conflictos
nano archivo_con_conflicto.py
# Busca las marcas: <<<<<<< HEAD, =======, >>>>>>>
# Resuelve manualmente
git add archivo_con_conflicto.py
git commit -m "Resolved conflicts"
```

### Error: "Module not found" después de actualizar

```bash
# Asegúrate de estar en el entorno virtual
source .venv/bin/activate

# Reinstala todas las dependencias
pip install -r requirements.txt --force-reinstall
```

### El servidor no arranca después de actualizar

```bash
# 1. Ver los logs para entender el error
screen -r whatsapp
# O
tail -50 whatsapp.log

# 2. Verificar el .env
cat .env
# Asegúrate que todas las variables están presentes

# 3. Verificar la base de datos
ls -la beansco.db

# 4. Probar manualmente
source .venv/bin/activate
python whatsapp_server.py
# Verás el error directamente
```

### Rollback (volver a versión anterior)

Si la actualización causó problemas:

```bash
# 1. Ver commits recientes
git log --oneline -5

# 2. Volver a un commit anterior
git reset --hard COMMIT_HASH

# 3. Restaurar backup de base de datos (si es necesario)
cp backups/FECHA/beansco.db beansco.db

# 4. Reiniciar servidor
./start_server.sh
```

---

## 🔐 Buenas Prácticas

### 1. Siempre hacer backup antes de actualizar

```bash
# Crear directorio de backups
mkdir -p backups

# Backup con timestamp
DATE=$(date +%Y%m%d_%H%M%S)
cp beansco.db backups/beansco.db.$DATE
cp .env backups/.env.$DATE
```

### 2. Probar en local antes de pushear

```bash
# En tu máquina local
source .venv/bin/activate
python test_whatsapp.py
python test_resolver.py
python test_full_flow.py
```

### 3. Usar mensajes de commit descriptivos

```bash
# ✅ Bien
git commit -m "Fix: resuelve bug de plural/singular en productos"
git commit -m "Feature: agrega endpoint de cancelación de ventas"
git commit -m "Docs: actualiza guía de deployment"

# ❌ Mal
git commit -m "fix"
git commit -m "cambios"
git commit -m "wip"
```

### 4. Verificar después de cada actualización

```bash
# Checklist post-actualización:
./check_server.sh           # ✅ Servidor corriendo
screen -r whatsapp          # ✅ Sin errores en logs
# Enviar mensaje de prueba  # ✅ Bot responde
```

---

## 🔄 Actualización con Zero Downtime

Para actualizar sin detener el servicio (avanzado):

```bash
# 1. Clonar el repo en un directorio temporal
git clone tu-repo.git /tmp/app-new

# 2. Configurar el nuevo deployment
cd /tmp/app-new
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp /ruta/original/.env .env
cp /ruta/original/beansco.db beansco.db

# 3. Iniciar nueva instancia en otro puerto (si aplica)
# ...

# 4. Cambiar symlink o swap directories
mv /ruta/app /ruta/app.old
mv /tmp/app-new /ruta/app

# 5. Reiniciar servidor
cd /ruta/app
./stop_server.sh
./start_server.sh

# 6. Si funciona, eliminar old
rm -rf /ruta/app.old
```

---

## 📊 Monitoreo Post-Actualización

### Verificar logs en tiempo real

```bash
# Ver logs mientras llegan mensajes
screen -r whatsapp

# O con tail
tail -f whatsapp.log

# Con systemd
sudo journalctl -u whatsapp-bot -f
```

### Métricas importantes a revisar

```bash
# 1. CPU y memoria
htop

# 2. Conexión a Green API
source .venv/bin/activate
python check_account.py

# 3. Últimos errores
tail -100 whatsapp.log | grep -i error

# 4. Ventas procesadas hoy
sqlite3 beansco.db "SELECT COUNT(*) FROM sales WHERE date(created_at) = date('now');"
```

---

## ⚡ Script de Actualización Rápida (Una Línea)

```bash
# Para cuando solo necesitas pull + restart rápido
./stop_server.sh && git pull && ./start_server.sh
```

---

## 📝 Checklist de Actualización

Usa este checklist cada vez que actualices:

- [ ] Commit y push de cambios locales
- [ ] SSH al VPS
- [ ] Ejecutar `./update.sh` (o pasos manuales)
- [ ] Verificar con `./check_server.sh`
- [ ] Ver logs: `screen -r whatsapp`
- [ ] Enviar mensaje de prueba
- [ ] Verificar respuesta del bot
- [ ] Monitorear logs por 5-10 minutos

---

## 🎯 Resumen Ejecutivo

**Actualización más común:**

```bash
# Local
git add . && git commit -m "mensaje" && git push

# VPS
ssh usuario@vps
cd proyecto
./update.sh
```

**Verificación rápida:**

```bash
./check_server.sh
screen -r whatsapp
# Enviar mensaje de prueba
```

**Si algo falla:**

```bash
# Ver logs
screen -r whatsapp

# Restaurar backup
cp backups/ULTIMO/beansco.db beansco.db

# Volver a commit anterior
git reset --hard COMMIT_ANTERIOR
./start_server.sh
```

---

¿Preguntas? Consulta [VPS_DEPLOYMENT.md](VPS_DEPLOYMENT.md) para más detalles.
