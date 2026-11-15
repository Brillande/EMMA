@echo off
rem Instala el paquete de modelos de EMMA (ver instalar.ps1). Doble clic o desde una consola.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
pause
