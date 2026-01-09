#!/bin/bash

# VPS Deployment Script
# Run this on your VPS: ./deploy-vps.sh

set -e

echo "========================================="
echo "  Beans&Co VPS Deployment"
echo "========================================="
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker not installed. Install with:"
    echo "  curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# Check .env
if [ ! -f .env ]; then
    echo "[ERROR] .env file not found"
    echo "  cp .env.example .env"
    echo "  nano .env  # Edit configuration"
    exit 1
fi

echo "[1/4] Stopping old containers..."
docker-compose -f docker-compose.production.yml down || true

echo "[2/4] Building images..."
docker-compose -f docker-compose.production.yml build

echo "[3/4] Starting services..."
docker-compose -f docker-compose.production.yml up -d

echo "[4/4] Checking health..."
sleep 15
docker-compose -f docker-compose.production.yml ps

echo ""
echo "========================================="
echo "  Deployment Complete!"
echo "========================================="
echo ""
echo "Access at: http://$(curl -s ifconfig.me)"
echo ""
echo "Logs: docker-compose -f docker-compose.production.yml logs -f"
echo ""
