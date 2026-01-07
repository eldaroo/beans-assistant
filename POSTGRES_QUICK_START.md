# PostgreSQL Setup - Quick Start

Migración rápida de SQLite a PostgreSQL con Docker.

## 🎯 Lo que vas a lograr

- Base de datos PostgreSQL en Docker en tu VPS
- Backend local conectado a la BD remota
- WhatsApp server en producción con acceso a la misma BD

## 📁 Archivos nuevos

| Archivo | Descripción |
|---------|-------------|
| `docker-compose.yml` | Configuración de PostgreSQL + pgAdmin en Docker |
| `postgres/init/01-schema.sql` | Schema de PostgreSQL (se ejecuta automáticamente) |
| `migrate_to_postgres.py` | Script para migrar datos de SQLite → PostgreSQL |
| `database_pg.py` | Capa de base de datos PostgreSQL (mismo API que database.py) |
| `database_config.py` | Selector automático entre SQLite/PostgreSQL |
| `connect_db_tunnel.sh` | Helper para crear túnel SSH seguro |
| `POSTGRES_DOCKER_DEPLOYMENT.md` | Guía completa paso a paso (LEER ESTA) |

## ⚡ Quick Start

### 1. En el VPS

```bash
# Conectar
ssh usuario@tu-vps.com
cd ~/supabase-sql-agent

# Configurar .env
cp .env.example .env
nano .env  # Agregar POSTGRES_PASSWORD

# Iniciar PostgreSQL
docker compose up -d postgres

# Migrar datos
python migrate_to_postgres.py \
  --db-url "postgresql://beansco:TU_PASSWORD@localhost:5432/beansco_main"
```

### 2. En tu computadora local

**Opción A: Túnel SSH (Recomendado)** 🔒

```bash
# Editar VPS_USER y VPS_HOST en connect_db_tunnel.sh
nano connect_db_tunnel.sh

# Conectar
bash connect_db_tunnel.sh &
```

**Opción B: Puerto expuesto** (menos seguro)

Ver sección "3.2" en `POSTGRES_DOCKER_DEPLOYMENT.md`

### 3. Configurar `.env` local

```bash
USE_POSTGRES=true
POSTGRES_HOST=localhost     # Si usas túnel SSH
POSTGRES_PORT=5432
POSTGRES_DB=beansco_main
POSTGRES_USER=beansco
POSTGRES_PASSWORD=TU_PASSWORD
```

### 4. Probar

```bash
# Verificar conexión
python -c "from database_config import db; print(db.fetch_one('SELECT 1'))"

# Iniciar backend
bash restart_backend.sh
```

## 🔄 Volver a SQLite

```bash
# En .env
USE_POSTGRES=false
```

El sistema automáticamente usa SQLite.

## 📖 Documentación completa

Lee **`POSTGRES_DOCKER_DEPLOYMENT.md`** para:
- Configuración de seguridad
- Troubleshooting
- Backups
- Monitoreo
- Y mucho más

## 🆘 Ayuda rápida

### PostgreSQL no arranca

```bash
docker compose logs postgres
docker compose restart postgres
```

### No puedo conectar desde local

```bash
# ¿Túnel SSH activo?
ps aux | grep "ssh -L 5432"

# ¿Password correcto?
cat .env | grep POSTGRES_PASSWORD

# Probar conexión
telnet localhost 5432
```

### Error "relation does not exist"

```bash
# Las tablas no se crearon. Recrear contenedor:
docker compose down -v
docker compose up -d postgres

# Re-migrar datos
python migrate_to_postgres.py --db-url "postgresql://..."
```

## 🚀 Siguiente nivel

- [ ] Configurar backups automáticos
- [ ] Instalar pgAdmin para gestión visual
- [ ] Configurar SSL para conexiones remotas
- [ ] Implementar connection pooling
- [ ] Monitoreo de performance

Ver `POSTGRES_DOCKER_DEPLOYMENT.md` para detalles.
