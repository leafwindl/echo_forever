@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0switch-server.ps1" %*
