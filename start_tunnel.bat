@echo off
REM Inicia túnel SSH en ventana minimizada
title PostgreSQL SSH Tunnel
powershell.exe -ExecutionPolicy Bypass -File "%~dp0keep_tunnel_alive.ps1"
