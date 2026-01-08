#!/bin/bash
# Script de despliegue para AWS

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Beans&Co - AWS Deployment Script   ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""

# Check required tools
command -v docker >/dev/null 2>&1 || { echo -e "${RED}Error: docker no está instalado${NC}" >&2; exit 1; }
command -v aws >/dev/null 2>&1 || { echo -e "${RED}Error: aws cli no está instalado${NC}" >&2; exit 1; }

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-east-1}

echo -e "${YELLOW}AWS Account:${NC} $AWS_ACCOUNT_ID"
echo -e "${YELLOW}AWS Region:${NC} $AWS_REGION"
echo ""

# Choose deployment type
echo "¿Qué quieres desplegar?"
echo "1) Backend (FastAPI)"
echo "2) WhatsApp Client"
echo "3) Ambos"
read -p "Selecciona (1/2/3): " DEPLOY_CHOICE

# ECR Login
echo -e "\n${YELLOW}[1/4] Login a ECR...${NC}"
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Deploy Backend
if [[ "$DEPLOY_CHOICE" == "1" ]] || [[ "$DEPLOY_CHOICE" == "3" ]]; then
    echo -e "\n${YELLOW}[2/4] Building Backend...${NC}"

    # Create ECR repo if it doesn't exist
    aws ecr describe-repositories --repository-names beansco-backend --region $AWS_REGION 2>/dev/null || \
        aws ecr create-repository --repository-name beansco-backend --region $AWS_REGION

    # Build
    docker build -f backend/Dockerfile -t beansco-backend .

    # Tag
    docker tag beansco-backend:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-backend:latest
    docker tag beansco-backend:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-backend:$(date +%Y%m%d-%H%M%S)

    # Push
    echo -e "${YELLOW}[3/4] Pushing Backend to ECR...${NC}"
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-backend:latest
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-backend:$(date +%Y%m%d-%H%M%S)

    echo -e "${GREEN}✓ Backend desplegado${NC}"
fi

# Deploy WhatsApp
if [[ "$DEPLOY_CHOICE" == "2" ]] || [[ "$DEPLOY_CHOICE" == "3" ]]; then
    echo -e "\n${YELLOW}[2/4] Building WhatsApp Client...${NC}"

    # Create ECR repo if it doesn't exist
    aws ecr describe-repositories --repository-names beansco-whatsapp --region $AWS_REGION 2>/dev/null || \
        aws ecr create-repository --repository-name beansco-whatsapp --region $AWS_REGION

    # Build
    docker build -f Dockerfile.whatsapp -t beansco-whatsapp .

    # Tag
    docker tag beansco-whatsapp:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-whatsapp:latest
    docker tag beansco-whatsapp:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-whatsapp:$(date +%Y%m%d-%H%M%S)

    # Push
    echo -e "${YELLOW}[3/4] Pushing WhatsApp to ECR...${NC}"
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-whatsapp:latest
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-whatsapp:$(date +%Y%m%d-%H%M%S)

    echo -e "${GREEN}✓ WhatsApp Client desplegado${NC}"
fi

echo -e "\n${YELLOW}[4/4] Deployment completo${NC}"
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║            ¡Despliegue exitoso!       ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo "Imágenes disponibles en ECR:"
if [[ "$DEPLOY_CHOICE" == "1" ]] || [[ "$DEPLOY_CHOICE" == "3" ]]; then
    echo "  - $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-backend:latest"
fi
if [[ "$DEPLOY_CHOICE" == "2" ]] || [[ "$DEPLOY_CHOICE" == "3" ]]; then
    echo "  - $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/beansco-whatsapp:latest"
fi
echo ""
echo "Próximos pasos:"
echo "1. Crear/actualizar ECS Task Definition"
echo "2. Actualizar ECS Service para usar la nueva imagen"
echo "3. Verificar logs en CloudWatch"
