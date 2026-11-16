@echo off
rem 打开 Echo Desktop 可视化客户端（无控制台窗口）
setlocal
set "ROOT=%~dp0"
set "PYTHONW=%ROOT%..\.venv\Scripts\pythonw.exe"
if exist "%PYTHONW%" (
  start "" "%PYTHONW%" "%ROOT%launch_client.py"
  exit /b 0
)
set "PYTHON=%ROOT%..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Python venv not found: %PYTHON%
  pause
  exit /b 1
)
"%PYTHON%" "%ROOT%launch_client.py"
