# Beans&Co Docker Deployment Guide

## Quick Start

### 1. Prepare your VPS

```bash
# SSH into your VPS
ssh root@31.97.100.1

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Clone your repository (or upload files)
git clone <your-repo> beansco
cd beansco
```

### 2. Configure Environment

```bash
# Copy and edit .env
cp .env.example .env
nano .env
```

**Important variables to set**:
```bash
# AI API
GOOGLE_API_KEY=your-google-api-key

# WhatsApp
GREEN_API_INSTANCE_ID=your-instance-id
GREEN_API_TOKEN=your-token

# Database (keep defaults for Docker)
USE_POSTGRES=true
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=beansco_main
POSTGRES_USER=beansco
POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD  # ⚠️ Change this!

# Redis
REDIS_ENABLED=true
REDIS_HOST=redis
REDIS_PORT=6379
```

### 3. Deploy

```bash
# Make deploy script executable
chmod +x deploy-vps.sh

# Run deployment
./deploy-vps.sh
```

### 4. Access

- **Admin Panel**: `http://YOUR_VPS_IP`
- **API Docs**: `http://YOUR_VPS_IP:8000/docs`

---

## Management Commands

### View Logs
```bash
# All services
docker-compose -f docker-compose.production.yml logs -f

# Specific service
docker-compose -f docker-compose.production.yml logs -f backend
docker-compose -f docker-compose.production.yml logs -f whatsapp-bot
```

### Restart Services
```bash
# All services
docker-compose -f docker-compose.production.yml restart

# Specific service
docker-compose -f docker-compose.production.yml restart backend
```

### Stop Everything
```bash
docker-compose -f docker-compose.production.yml down
```

### Update Code
```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose -f docker-compose.production.yml up -d --build
```

---

## Architecture

```
┌─────────────────────────────────────────┐
│           Nginx (Port 80/443)           │
│         Reverse Proxy + SSL             │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐  ┌─────▼──────┐
│   Backend   │  │  WhatsApp  │
│  (FastAPI)  │  │    Bot     │
│  Port 8000  │  │            │
└──────┬──────┘  └─────┬──────┘
       │                │
       └───────┬────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐  ┌─────▼──────┐
│  PostgreSQL │  │   Redis    │
│  Port 5432  │  │  Port 6379 │
└─────────────┘  └────────────┘
```

---

## Troubleshooting

### Backend won't start
```bash
# Check logs
docker-compose -f docker-compose.production.yml logs backend

# Common issues:
# - Missing GOOGLE_API_KEY in .env
# - PostgreSQL not ready (wait 30s and retry)
```

### Database connection errors
```bash
# Check PostgreSQL is running
docker-compose -f docker-compose.production.yml ps postgres

# Check PostgreSQL logs
docker-compose -f docker-compose.production.yml logs postgres

# Reset database (⚠️ deletes all data)
docker-compose -f docker-compose.production.yml down -v
docker-compose -f docker-compose.production.yml up -d
```

### WhatsApp bot not responding
```bash
# Check bot logs
docker-compose -f docker-compose.production.yml logs whatsapp-bot

# Restart bot
docker-compose -f docker-compose.production.yml restart whatsapp-bot
```

---

## SSL/HTTPS Setup (Optional but Recommended)

### Using Certbot (Let's Encrypt)

```bash
# Install Certbot
sudo apt-get install certbot

# Get certificate (replace with your domain)
sudo certbot certonly --standalone -d your-domain.com

# Certificates will be in:
# /etc/letsencrypt/live/your-domain.com/

# Copy to nginx directory
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/

# Uncomment HTTPS section in nginx/nginx.conf
# Restart nginx
docker-compose -f docker-compose.production.yml restart nginx
```

---

## Backup

### Database Backup
```bash
# Backup
docker exec beansco-postgres pg_dump -U beansco beansco_main > backup.sql

# Restore
docker exec -i beansco-postgres psql -U beansco beansco_main < backup.sql
```

### Full Backup
```bash
# Backup data volumes
docker run --rm -v beansco_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres-backup.tar.gz /data
```

---

## Monitoring

### Resource Usage
```bash
# Container stats
docker stats

# Disk usage
docker system df
```

### Health Checks
```bash
# Check all services are healthy
docker-compose -f docker-compose.production.yml ps

# Test backend
curl http://localhost:8000/health

# Test admin panel
curl http://localhost/
```

---

## Migration to AWS

When ready to migrate to AWS:

1. **Push Docker images to ECR**
2. **Use AWS ECS** (simpler than Kubernetes)
3. **RDS for PostgreSQL** (managed database)
4. **ElastiCache for Redis** (managed cache)
5. **ALB for load balancing** (instead of Nginx)

The Docker Compose file will translate easily to ECS task definitions.

---

## Support

For issues, check:
1. Logs: `docker-compose logs -f`
2. Service status: `docker-compose ps`
3. Resource usage: `docker stats`
