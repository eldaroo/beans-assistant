@echo off
setlocal

set "ROOT=%~1"
set "BACKEND_URL_ARG=%~2"

if "%ROOT%"=="" set "ROOT=%~dp0"
if "%BACKEND_URL_ARG%"=="" set "BACKEND_URL_ARG=http://127.0.0.1:8000"

cd /d "%ROOT%whatsapp_baileys"

where node >nul 2>&1
if errorlevel 1 (
  echo [WhatsApp] ERROR: Node.js no encontrado en PATH.
  echo [WhatsApp] Instala Node.js 20+ y reintenta.
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [WhatsApp] ERROR: npm no encontrado en PATH.
  echo [WhatsApp] Reinstala Node.js con npm y reintenta.
  pause
  exit /b 1
)

if not exist node_modules (
  echo [WhatsApp] Installing node modules...
  call npm install --omit=dev
  if errorlevel 1 (
    echo [WhatsApp] ERROR: fallo npm install.
    pause
    exit /b 1
  )
)

set "BACKEND_URL=%BACKEND_URL_ARG%"
set "BAILEYS_AUTO_CREATE_TENANT=true"

echo [WhatsApp] Starting Baileys connector...
echo [WhatsApp] BACKEND_URL=%BACKEND_URL%
node server.js

echo.
echo [WhatsApp] Finalizo (exit code %errorlevel%).
pause

endlocal
