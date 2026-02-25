@echo off
setlocal

set "ROOT=%~1"
set "PYTHON_EXE=%~2"
set "BACKEND_HOST=%~3"
set "BACKEND_PORT=%~4"

if "%ROOT%"=="" set "ROOT=%~dp0"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=python"
if "%BACKEND_HOST%"=="" set "BACKEND_HOST=127.0.0.1"
if "%BACKEND_PORT%"=="" set "BACKEND_PORT=8000"

cd /d "%ROOT%"

echo [Backend] Starting uvicorn on http://%BACKEND_HOST%:%BACKEND_PORT%...
"%PYTHON_EXE%" -m uvicorn backend.app:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload

echo.
echo [Backend] Finalizo (exit code %errorlevel%).
pause

endlocal
