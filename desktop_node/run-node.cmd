@echo off
rem 启动 Echo Desktop 节点（无界面），跟随 %APPDATA%\EchoDesktop\config.json
rem 想切换服务器：先运行 switch-server.cmd prod 或 switch-server.cmd local
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Python venv not found: %PYTHON%
  pause
  exit /b 1
)
set "PYTHONPATH=%ROOT%"
"%PYTHON%" -B -m echo_desktop run
pause
