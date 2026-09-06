@echo off
wsl.exe --cd "%~dp0." --exec sh scripts/run-wsl-ui.sh
if errorlevel 1 pause
