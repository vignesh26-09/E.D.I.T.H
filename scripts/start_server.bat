@echo off
REM E.D.I.T.H. Brain Core Windows Service Startup Script (Batch)
REM Binds to loopback interface 127.0.0.1 for local trust boundary enforcement.

setlocal
set PROJECT_ROOT=%~dp0..
cd /d "%PROJECT_ROOT%"

echo ==========================================================
echo  E.D.I.T.H. Brain Core - Starting Local Intelligence Service
echo  Host: 127.0.0.1 ^| Port: 8000
echo  Directory: %PROJECT_ROOT%
echo ==========================================================

set PYTHONPATH=%PROJECT_ROOT%\src;%PYTHONPATH%

python -m uvicorn edith_brain.api.app:create_app --factory --host 127.0.0.1 --port 8000

endlocal
