# Script para subir archivos al VPS y desplegar

$VPS_USER = "root"
$VPS_HOST = "31.97.100.1"
$VPS_DIR = "/root/beansco"
$LOCAL_DIR = "C:\Users\loko_\supabase-sql-agent"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  DEPLOYMENT TO VPS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "[ERROR] .env file not found" -ForegroundColor Red
    Write-Host "Creating from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "IMPORTANT: Edit .env and configure:" -ForegroundColor Yellow
    Write-Host "  - GOOGLE_API_KEY" -ForegroundColor White
    Write-Host "  - GREEN_API_INSTANCE_ID" -ForegroundColor White
    Write-Host "  - GREEN_API_TOKEN" -ForegroundColor White
    Write-Host "  - POSTGRES_PASSWORD (change from default)" -ForegroundColor White
    Write-Host ""
    Write-Host "Then run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/5] Preparing files..." -ForegroundColor Yellow

# Create .dockerignore if not exists
$dockerignore = @"
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info
dist
build
.git
.gitignore
.vscode
.idea
*.log
.env.local
venv
env
*.db-journal
*.db-wal
*.db-shm
node_modules
.DS_Store
"@

$dockerignore | Out-File -FilePath ".dockerignore" -Encoding UTF8

Write-Host "  [OK] .dockerignore created" -ForegroundColor Green

Write-Host ""
Write-Host "[2/5] Creating deployment package..." -ForegroundColor Yellow

# Files to upload
$filesToUpload = @(
    "backend",
    "configs",
    "data",
    "*.py",
    "requirements.txt",
    "Dockerfile",
    "Dockerfile.whatsapp",
    "docker-compose.production.yml",
    "deploy-vps.sh",
    ".env",
    "nginx"
)

Write-Host "  [OK] Package ready" -ForegroundColor Green

Write-Host ""
Write-Host "[3/5] Connecting to VPS..." -ForegroundColor Yellow
Write-Host "  Host: $VPS_HOST" -ForegroundColor Gray

# Test SSH connection
$sshTest = ssh -o ConnectTimeout=5 -o BatchMode=yes $VPS_USER@$VPS_HOST "echo OK" 2>&1
if ($sshTest -ne "OK") {
    Write-Host "  [WARNING] SSH requires password" -ForegroundColor Yellow
    Write-Host "  You will be prompted for password during upload" -ForegroundColor Gray
}

Write-Host ""
Write-Host "[4/5] Uploading files to VPS..." -ForegroundColor Yellow
Write-Host "  This may take a few minutes..." -ForegroundColor Gray

# Create directory on VPS
ssh $VPS_USER@$VPS_HOST "mkdir -p $VPS_DIR"

# Upload files using rsync (faster than scp)
$rsyncAvailable = Get-Command rsync -ErrorAction SilentlyContinue
if ($rsyncAvailable) {
    Write-Host "  Using rsync for faster upload..." -ForegroundColor Gray
    rsync -avz --progress `
        --exclude '__pycache__' `
        --exclude '*.pyc' `
        --exclude '.git' `
        --exclude 'venv' `
        --exclude '*.log' `
        ./ ${VPS_USER}@${VPS_HOST}:${VPS_DIR}/
} else {
    Write-Host "  Using scp (install rsync for faster uploads)..." -ForegroundColor Gray
    scp -r * ${VPS_USER}@${VPS_HOST}:${VPS_DIR}/
}

Write-Host "  [OK] Files uploaded" -ForegroundColor Green

Write-Host ""
Write-Host "[5/5] Deploying on VPS..." -ForegroundColor Yellow

# Run deployment script on VPS
ssh $VPS_USER@$VPS_HOST "cd $VPS_DIR && chmod +x deploy-vps.sh && ./deploy-vps.sh"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access your application at:" -ForegroundColor Cyan
Write-Host "  http://$VPS_HOST" -ForegroundColor White
Write-Host ""
Write-Host "Useful commands (run on VPS):" -ForegroundColor Yellow
Write-Host "  ssh $VPS_USER@$VPS_HOST" -ForegroundColor Gray
Write-Host "  cd $VPS_DIR" -ForegroundColor Gray
Write-Host "  docker-compose -f docker-compose.production.yml logs -f" -ForegroundColor Gray
Write-Host ""
