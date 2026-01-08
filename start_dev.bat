@echo off
REM Inicia todo el entorno de desarrollo (túnel + backend)
title Entorno de Desarrollo
powershell.exe -ExecutionPolicy Bypass -File "%~dp0start_dev.ps1"
pause
