# PostgreSQL + Docker Deployment Guide

Guía completa para migrar de SQLite a PostgreSQL en Docker y conectar tu aplicación local a la base de datos remota.

## 🎯 Arquitectura

```
📍 TU COMPUTADORA (Local)              📍 VPS (Producción)
├─ Backend FastAPI (local)             ├─ Docker Compose
│  └─ Conecta a PostgreSQL remoto      │  ├─ PostgreSQL (puerto 5432)
├─ WhatsApp Client (local)             │  └─ Volúmenes persistentes
└─ .env (con POSTGRES_HOST=tu-vps)     │
                                       ├─ WhatsApp Server
                                       │  └─ Conecta a PostgreSQL local
                                       └─ Firewall/Security
```

**Ventajas:**
- ✅ Una sola base de datos centralizada
- ✅ Backend local siempre actualizado
- ✅ WhatsApp server en producción
- ✅ Datos en tiempo real
- ✅ Fácil de escalar

---

## 📋 Paso 1: Setup en el VPS

### 1.1. Instalar Docker y Docker Compose

Conectate al VPS:

```bash
ssh usuario@tu-vps.com
cd ~/supabase-sql-agent
```

Instalar Docker:

```bash
# Actualizar paquetes
sudo apt update && sudo apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Agregar tu usuario al grupo docker
sudo usermod -aG docker $USER

# Aplicar cambios (o cerrar sesión y volver a entrar)
newgrp docker

# Verificar instalación
docker --version
docker compose version
```

### 1.2. Configurar variables de entorno

Crear archivo `.env` en el VPS:

```bash
cd ~/supabase-sql-agent
nano .env
```

Agregar:

```bash
# PostgreSQL Configuration
POSTGRES_PASSWORD=TU_PASSWORD_SEGURO_AQUI  # ⚠️ CAMBIAR ESTO
PGADMIN_PASSWORD=TU_PASSWORD_PGADMIN       # Solo si usas pgAdmin

# Application
USE_POSTGRES=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=beansco_main
POSTGRES_USER=beansco
POSTGRES_SCHEMA=public

# Green API WhatsApp
GREEN_API_INSTANCE_ID=tu-instance-id
GREEN_API_TOKEN=tu-api-token

# Google/Gemini API
GOOGLE_API_KEY=tu-api-key
```

Guardar: `Ctrl+O`, Enter, `Ctrl+X`

### 1.3. Iniciar PostgreSQL con Docker

```bash
# Iniciar PostgreSQL
docker compose up -d postgres

# Ver logs
docker compose logs -f postgres

# Verificar que está corriendo
docker compose ps
```

Deberías ver:

```
NAME                 COMMAND                  SERVICE      STATUS
beansco-postgres     "docker-entrypoint.s…"   postgres     Up
```

### 1.4. Verificar conexión a PostgreSQL

```bash
# Conectarse al contenedor
docker exec -it beansco-postgres psql -U beansco -d beansco_main

# Deberías ver el prompt de PostgreSQL:
# beansco_main=#

# Listar tablas
\dt

# Salir
\q
```

---

## 📊 Paso 2: Migrar datos de SQLite a PostgreSQL

### 2.1. Instalar dependencias Python (si no lo hiciste)

En el VPS:

```bash
cd ~/supabase-sql-agent
source .venv/bin/activate
pip install psycopg2-binary
```

### 2.2. Ejecutar migración

**Opción A: Migrar la base de datos principal**

```bash
python migrate_to_postgres.py \
  --db-url "postgresql://beansco:TU_PASSWORD@localhost:5432/beansco_main" \
  --main-db beansco.db
```

**Opción B: Migrar todos los tenants**

```bash
python migrate_to_postgres.py \
  --db-url "postgresql://beansco:TU_PASSWORD@localhost:5432/beansco_main" \
  --tenants-dir data/clients
```

**Opción C: Migrar un tenant específico**

```bash
python migrate_to_postgres.py \
  --db-url "postgresql://beansco:TU_PASSWORD@localhost:5432/beansco_main" \
  --tenant-phone "+5491112345678"
```

### 2.3. Verificar migración

```bash
# Conectarse a PostgreSQL
docker exec -it beansco-postgres psql -U beansco -d beansco_main

# Ver esquemas (para multi-tenant)
\dn

# Ver tablas en el esquema public
\dt

# Contar productos migrados
SELECT COUNT(*) FROM products;

# Ver algunos productos
SELECT id, sku, name FROM products LIMIT 5;

# Salir
\q
```

---

## 🔐 Paso 3: Configurar acceso remoto seguro

### 3.1. Opción A: Túnel SSH (Recomendado - Más seguro) 🔒

**No expongas el puerto 5432 a internet**. En su lugar, usa un túnel SSH.

#### En tu computadora local (Windows):

Crear un script `connect_db.sh`:

```bash
#!/bin/bash
ssh -L 5432:localhost:5432 usuario@tu-vps.com -N
```

Ejecutar:

```bash
bash connect_db.sh
```

Ahora `localhost:5432` en tu computadora apunta al PostgreSQL del VPS.

**En tu `.env` local:**

```bash
USE_POSTGRES=true
POSTGRES_HOST=localhost  # ← El túnel SSH redirige aquí
POSTGRES_PORT=5432
POSTGRES_DB=beansco_main
POSTGRES_USER=beansco
POSTGRES_PASSWORD=TU_PASSWORD
```

### 3.2. Opción B: Exponer puerto con firewall (Menos seguro) ⚠️

Si no querés usar túnel SSH:

#### En el VPS:

```bash
# Editar PostgreSQL para escuchar en todas las interfaces
docker compose down
```

Editar `docker-compose.yml`:

```yaml
services:
  postgres:
    # ... (configuración existente)
    environment:
      POSTGRES_HOST_AUTH_METHOD: md5  # O usar "scram-sha-256"
    command: postgres -c listen_addresses='*'
```

Crear/editar `postgres/init/02-pg_hba.conf`:

```
# TYPE  DATABASE        USER            ADDRESS                 METHOD
host    all             all             0.0.0.0/0               md5
host    all             all             ::/0                    md5
```

Reiniciar:

```bash
docker compose up -d postgres
```

#### Configurar firewall:

```bash
# Opción 1: Permitir solo tu IP
sudo ufw allow from TU_IP_PUBLICA to any port 5432

# Opción 2: Permitir cualquier IP (NO RECOMENDADO)
sudo ufw allow 5432/tcp

# Ver reglas
sudo ufw status
```

**En tu `.env` local:**

```bash
USE_POSTGRES=true
POSTGRES_HOST=tu-vps.com  # ← IP pública o dominio
POSTGRES_PORT=5432
POSTGRES_DB=beansco_main
POSTGRES_USER=beansco
POSTGRES_PASSWORD=TU_PASSWORD
```

---

## 🖥️ Paso 4: Configurar tu aplicación local

### 4.1. Actualizar `.env` local

En tu computadora (Windows):

```bash
cd C:\Users\loko_\supabase-sql-agent
notepad .env
```

Agregar/actualizar:

```bash
# Database - PostgreSQL remoto
USE_POSTGRES=true
POSTGRES_HOST=localhost  # Si usas túnel SSH
# POSTGRES_HOST=tu-vps.com  # Si exponés el puerto
POSTGRES_PORT=5432
POSTGRES_DB=beansco_main
POSTGRES_USER=beansco
POSTGRES_PASSWORD=TU_PASSWORD
POSTGRES_SCHEMA=public

# Green API (opcional para local)
GREEN_API_INSTANCE_ID=tu-instance-id
GREEN_API_TOKEN=tu-api-token

# Google/Gemini API
GOOGLE_API_KEY=tu-api-key
```

### 4.2. Actualizar código para usar PostgreSQL

El proyecto ya está configurado para detectar automáticamente qué base usar.

**Para backend FastAPI**, verificar que use `database_config`:

```python
# backend/api/*.py - Cambiar esta línea:
import database

# Por esta:
from database_config import db as database
```

O alternativamente, actualizar imports en todos los archivos del backend.

### 4.3. Probar conexión local

```bash
# Activar túnel SSH (si usas esa opción)
bash connect_db.sh

# En otra terminal, probar conexión
python -c "from database_config import db; print(db.fetch_one('SELECT 1'))"
```

Debería mostrar: `{'?column?': 1}`

### 4.4. Iniciar backend local

```bash
# Windows
bash restart_backend.sh
```

El backend local ahora está conectado a la base de datos del VPS! 🎉

---

## 🚀 Paso 5: Iniciar WhatsApp Server en el VPS

En el VPS:

```bash
cd ~/supabase-sql-agent

# Usar screen para mantener el proceso corriendo
screen -S whatsapp

# Activar entorno virtual
source .venv/bin/activate

# Iniciar servidor
python whatsapp_server_multitenant.py

# Detach: Ctrl+A, luego D
```

Para reconectar:

```bash
screen -r whatsapp
```

---

## ✅ Verificación completa

### En el VPS:

```bash
# ¿PostgreSQL está corriendo?
docker compose ps

# ¿Hay datos?
docker exec -it beansco-postgres psql -U beansco -d beansco_main -c "SELECT COUNT(*) FROM products;"

# ¿WhatsApp server está corriendo?
screen -ls
```

### En tu computadora local:

```bash
# ¿Túnel SSH está activo? (si lo usas)
ps aux | grep "ssh -L"

# ¿Backend local conecta a PostgreSQL?
curl http://localhost:8000/health

# ¿Puedo ver productos?
curl http://localhost:8000/tenants
```

---

## 🔄 Flujo de trabajo diario

### En tu computadora (desarrollo):

```bash
# 1. Conectar túnel SSH (si usas túnel)
bash connect_db.sh &

# 2. Iniciar backend local
bash restart_backend.sh

# 3. Trabajar normalmente - todos los cambios van a la BD remota
```

### En el VPS (producción):

```bash
# Solo necesitas el WhatsApp server corriendo
screen -r whatsapp  # Para ver logs
```

---

## 🛠️ Comandos útiles

### Docker:

```bash
# Ver logs de PostgreSQL
docker compose logs -f postgres

# Reiniciar PostgreSQL
docker compose restart postgres

# Detener todo
docker compose down

# Iniciar con rebuild
docker compose up -d --build

# Ver uso de recursos
docker stats
```

### PostgreSQL:

```bash
# Backup
docker exec beansco-postgres pg_dump -U beansco beansco_main > backup.sql

# Restore
cat backup.sql | docker exec -i beansco-postgres psql -U beansco -d beansco_main

# Conectarse
docker exec -it beansco-postgres psql -U beansco -d beansco_main
```

### Túnel SSH:

```bash
# Verificar que está corriendo
ps aux | grep "ssh -L 5432"

# Cerrar túnel
pkill -f "ssh -L 5432"
```

---

## 🐛 Troubleshooting

### Error: "Connection refused"

```bash
# Verificar que PostgreSQL está corriendo
docker compose ps

# Ver logs
docker compose logs postgres

# Reiniciar
docker compose restart postgres
```

### Error: "Authentication failed"

```bash
# Verificar password en .env
cat .env | grep POSTGRES_PASSWORD

# Verificar que el usuario existe
docker exec -it beansco-postgres psql -U postgres -c "\du"
```

### Error: "Relation does not exist"

```bash
# Verificar que las tablas existen
docker exec -it beansco-postgres psql -U beansco -d beansco_main -c "\dt"

# Si no existen, el schema no se creó. Reiniciar:
docker compose down -v  # ⚠️ Esto borra los datos
docker compose up -d postgres
```

### Backend local no conecta

```bash
# ¿Túnel SSH está activo?
ps aux | grep "ssh -L 5432"

# ¿Firewall bloquea?
telnet tu-vps.com 5432

# ¿Password correcto en .env local?
cat .env | grep POSTGRES_PASSWORD
```

---

## 🎯 Próximos pasos

1. **Configurar backups automáticos:**
   ```bash
   # Agregar a crontab en el VPS
   0 2 * * * docker exec beansco-postgres pg_dump -U beansco beansco_main > /backup/db_$(date +\%Y\%m\%d).sql
   ```

2. **Monitoreo:**
   - Instalar pgAdmin (ya incluido en docker-compose con `--profile tools`)
   - Configurar alertas de espacio en disco

3. **Seguridad:**
   - Cambiar password de PostgreSQL regularmente
   - Usar certificados SSL para conexiones remotas
   - Configurar fail2ban para proteger SSH

4. **Performance:**
   - Ajustar `shared_buffers`, `work_mem` en PostgreSQL
   - Configurar índices adicionales según uso
   - Usar connection pooling (PgBouncer)

---

## 📊 Migración de vuelta a SQLite (opcional)

Si alguna vez querés volver a SQLite:

```bash
# En .env
USE_POSTGRES=false

# El sistema automáticamente usará database.py (SQLite)
```

Para exportar datos:

```bash
# Desde PostgreSQL
docker exec beansco-postgres pg_dump -U beansco beansco_main --data-only > data.sql

# Convertir a SQLite (necesita herramienta externa)
pgloader data.sql sqlite:///beansco.db
```

---

¡Listo! Ahora tenés una arquitectura robusta con:
- ✅ PostgreSQL en Docker en el VPS
- ✅ Backend local conectado a BD remota
- ✅ WhatsApp server en producción
- ✅ Datos centralizados y seguros
