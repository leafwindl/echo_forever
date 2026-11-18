@echo off
setlocal
title EchoComputer 控制台
echo 正在打开 EchoComputer 的 VM 控制台窗口（需要管理员权限）...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process vmconnect -Verb RunAs -ArgumentList 'localhost','EchoComputer'"
exit /b 0
