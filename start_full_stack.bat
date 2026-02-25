@echo off
setlocal

REM Start full local stack on Windows:
REM 1) Backend API (FastAPI + Admin UI)
REM 2) WhatsApp connector (Baileys)
REM 3) Open frontend/admin in browser

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ==========================================
echo   Beans Assistant - Full Stack Startup
echo ==========================================
echo.

if not exist ".env" (
  echo [INFO] .env no existe. Creando desde .env.example...
  copy ".env.example" ".env" >nul
  echo [WARN] Revisa .env y completa GOOGLE_API_KEY antes de usar el bot.
  echo.
)

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%venv\Scripts\python.exe"
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"
set "BACKEND_URL=http://%BACKEND_HOST%:%BACKEND_PORT%"

echo [PRE] Verificando dependencias de Python...
"%PYTHON_EXE%" -c "import fastapi, uvicorn, langgraph" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Faltan dependencias. Instalando...
  "%PYTHON_EXE%" -m pip install --upgrade pip
  if errorlevel 1 (
    echo [ERROR] No se pudo actualizar pip con %PYTHON_EXE%.
    echo [ERROR] Revisa tu entorno Python y vuelve a intentar.
    pause
    exit /b 1
  )

  "%PYTHON_EXE%" -m pip install -r requirements.txt -r backend\requirements.txt
  if errorlevel 1 (
    echo [ERROR] Fallo instalando dependencias.
    echo [ERROR] Ejecuta manualmente:
    echo         "%PYTHON_EXE%" -m pip install -r requirements.txt -r backend\requirements.txt
    pause
    exit /b 1
  )
)

echo [1/3] Iniciando backend en nueva ventana...
start "Beans Backend" cmd /k ""%ROOT%start_backend_local.bat" "%ROOT%" "%PYTHON_EXE%" "%BACKEND_HOST%" "%BACKEND_PORT%""

echo [2/3] Iniciando conector WhatsApp en nueva ventana...
start "Beans WhatsApp" cmd /k ""%ROOT%start_whatsapp_local.bat" "%ROOT%" "%BACKEND_URL%""

echo [3/3] Abriendo frontend/admin...
timeout /t 4 >nul
start "" "%BACKEND_URL%"

echo.
echo Listo. Ventanas abiertas:
echo - Beans Backend
echo - Beans WhatsApp
echo.
echo URLs:
echo - Frontend/Admin: %BACKEND_URL%
echo - API Docs:       %BACKEND_URL%/docs
echo.
echo Para detener:
echo - Cierra las ventanas "Beans Backend" y "Beans WhatsApp"
echo - o usa: taskkill /FI "WINDOWTITLE eq Beans Backend*" /T /F
echo - o usa: taskkill /FI "WINDOWTITLE eq Beans WhatsApp*" /T /F
echo.

endlocal
