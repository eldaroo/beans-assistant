@echo off
setlocal enabledelayedexpansion

cd /d "c:\Users\loko_\OneDrive\Desktop\Escritorio\beans-assistant"

echo Activating venv...
call .venv\Scripts\activate.bat

echo.
echo Running debug trace...
python debug_whatsapp_full.py

pause
