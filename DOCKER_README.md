# Docker Containers - Guía de Despliegue

## Resumen de Containers

Tu aplicación necesita **2 containers principales**:

```
┌─────────────────────────────────────┐
│  Container 1: BACKEND (FastAPI)    │
│  - Puerto: 8000                    │
│  - Imagen: beansco-backend         │
│  - Stateless                       │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Container 2: WHATSAPP CLIENT      │
│  - Sin puerto expuesto             │
│  - Imagen: beansco-whatsapp        │
│  - Stateful (persiste sesión)      │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  PostgreSQL (RDS en AWS)           │
│  - Puerto: 5432                    │
│  - (container local solo dev)      │
└─────────────────────────────────────┘
```

## Desarrollo Local

### Iniciar todo (con PostgreSQL local)

```bash
# 1. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 2. Build de imágenes
docker-compose build

# 3. Iniciar todos los servicios
docker-compose up -d

# 4. Ver logs
docker-compose logs -f

# 5. Acceder:
# - Backend: http://localhost:8000
# - Admin Panel: http://localhost:8000/
# - API Docs: http://localhost:8000/docs
# - PgAdmin: http://localhost:5050 (si usas --profile tools)
```

### Comandos útiles

```bash
# Ver estado de containers
docker-compose ps

# Reiniciar un servicio específico
docker-compose restart backend
docker-compose restart whatsapp

# Ver logs de un servicio
docker-compose logs -f backend
docker-compose logs -f whatsapp

# Entrar a un container
docker-compose exec backend bash
docker-compose exec whatsapp bash

# Detener todo
docker-compose down

# Detener y eliminar volúmenes (CUIDADO: borra datos)
docker-compose down -v
```

## Producción (AWS)

### Opción 1: EC2 con Docker Compose

```bash
# En tu EC2:
cd /home/ubuntu/supabase-sql-agent

# Configurar .env con credenciales de RDS
cat > .env << EOF
POSTGRES_HOST=your-rds-endpoint.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_DB=beansco_main
POSTGRES_USER=beansco
POSTGRES_PASSWORD=your_secure_password
ANTHROPIC_API_KEY=your_key
EOF

# Usar docker-compose de producción (sin PostgreSQL)
docker-compose -f docker-compose.prod.yml up -d
```

### Opción 2: ECS (Elastic Container Service)

#### 1. Build y Push a ECR

```bash
# Login a ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

# Crear repositorios
aws ecr create-repository --repository-name beansco-backend
aws ecr create-repository --repository-name beansco-whatsapp

# Build backend
docker build -f backend/Dockerfile -t beansco-backend .
docker tag beansco-backend:latest YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/beansco-backend:latest
docker push YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/beansco-backend:latest

# Build whatsapp
docker build -f Dockerfile.whatsapp -t beansco-whatsapp .
docker tag beansco-whatsapp:latest YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/beansco-whatsapp:latest
docker push YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/beansco-whatsapp:latest
```

#### 2. Crear ECS Task Definition (JSON)

Archivo: `ecs-task-definition.json`

```json
{
  "family": "beansco-app",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/beansco-backend:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "USE_POSTGRES", "value": "true"},
        {"name": "POSTGRES_HOST", "value": "your-rds-endpoint.rds.amazonaws.com"},
        {"name": "POSTGRES_PORT", "value": "5432"},
        {"name": "POSTGRES_DB", "value": "beansco_main"},
        {"name": "POSTGRES_USER", "value": "beansco"}
      ],
      "secrets": [
        {
          "name": "POSTGRES_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:beansco/postgres"
        },
        {
          "name": "ANTHROPIC_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:beansco/anthropic"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/beansco-backend",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "backend"
        }
      }
    },
    {
      "name": "whatsapp",
      "image": "YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/beansco-whatsapp:latest",
      "essential": true,
      "environment": [
        {"name": "USE_POSTGRES", "value": "true"},
        {"name": "POSTGRES_HOST", "value": "your-rds-endpoint.rds.amazonaws.com"},
        {"name": "POSTGRES_PORT", "value": "5432"},
        {"name": "POSTGRES_DB", "value": "beansco_main"},
        {"name": "POSTGRES_USER", "value": "beansco"},
        {"name": "BACKEND_URL", "value": "http://localhost:8000"}
      ],
      "secrets": [
        {
          "name": "POSTGRES_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:beansco/postgres"
        },
        {
          "name": "ANTHROPIC_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:beansco/anthropic"
        }
      ],
      "mountPoints": [
        {
          "sourceVolume": "whatsapp-auth",
          "containerPath": "/app/.wwebjs_auth"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/beansco-whatsapp",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "whatsapp"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "whatsapp-auth",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXX",
        "transitEncryption": "ENABLED"
      }
    }
  ]
}
```

**IMPORTANTE para WhatsApp:** Necesitas EFS (Elastic File System) para persistir la sesión de WhatsApp entre reinicios.

#### 3. Crear ECS Service

```bash
# Registrar task definition
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json

# Crear servicio
aws ecs create-service \
  --cluster beansco-cluster \
  --service-name beansco-service \
  --task-definition beansco-app \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

## Volúmenes Importantes

### `whatsapp_auth` - CRÍTICO ⚠️

Este volumen almacena la sesión de WhatsApp. **Si se pierde, hay que escanear el QR de nuevo**.

```bash
# Backup del volumen (desarrollo local)
docker run --rm -v beansco_whatsapp_auth:/data -v $(pwd):/backup alpine tar czf /backup/whatsapp_backup.tar.gz /data

# Restore
docker run --rm -v beansco_whatsapp_auth:/data -v $(pwd):/backup alpine tar xzf /backup/whatsapp_backup.tar.gz -C /
```

En AWS ECS, usa **EFS** (Elastic File System) para este volumen.

## Troubleshooting

### Backend no arranca

```bash
# Ver logs
docker-compose logs backend

# Verificar conexión a PostgreSQL
docker-compose exec backend python -c "from database_config import db; print(db.fetch_one('SELECT 1'))"
```

### WhatsApp no conecta

```bash
# Ver logs
docker-compose logs whatsapp

# Verificar que puede comunicarse con backend
docker-compose exec whatsapp curl http://backend:8000/health
```

### PostgreSQL no acepta conexiones

```bash
# Verificar que está corriendo
docker-compose ps postgres

# Ver logs
docker-compose logs postgres

# Test de conexión
docker-compose exec postgres psql -U beansco -d beansco_main -c "SELECT version();"
```

## Arquitectura de Red

Los containers se comunican por la red interna `beansco-network`:

```
whatsapp container -> http://backend:8000 (nombre de servicio)
backend container -> postgres:5432 (desarrollo) o RDS endpoint (producción)
```

## Variables de Entorno Requeridas

```bash
# .env file
USE_POSTGRES=true
POSTGRES_HOST=postgres  # o RDS endpoint en producción
POSTGRES_PORT=5432
POSTGRES_DB=beansco_main
POSTGRES_USER=beansco
POSTGRES_PASSWORD=changeme123  # cambiar en producción
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

## Costos AWS Estimados

### Opción 1: EC2 + Docker Compose
- EC2 t3.small: ~$15/mes
- RDS db.t3.micro: ~$15/mes
- **Total: ~$30/mes**

### Opción 2: ECS Fargate
- Fargate (0.5 vCPU, 1GB RAM): ~$35/mes
- RDS db.t3.micro: ~$15/mes
- EFS (1GB para WhatsApp auth): ~$0.30/mes
- **Total: ~$50/mes**

Con **AWS Free Tier** (primeros 12 meses):
- EC2 750 horas/mes gratis (t3.micro)
- RDS 750 horas/mes gratis (db.t3.micro)
- **Total: ~$0-5/mes**
