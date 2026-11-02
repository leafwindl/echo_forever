@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Python venv not found: %PYTHON%
  echo Run this from the Echo repository, or install dependencies in desktop_node.
  pause
  exit /b 1
)
set "PYTHONPATH=%ROOT%"
"%PYTHON%" -B -m echo_desktop client
pause
