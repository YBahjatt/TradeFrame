@echo off
setlocal
set "BACKEND_URL=%~1"
set "FRONTEND_PORT=%~2"
echo TradeFrame Frontend
echo Path: %~dp0frontend
echo URL: http://127.0.0.1:%FRONTEND_PORT%/
cd /d "%~dp0frontend"
set "TRADEFRAME_BACKEND_URL=%BACKEND_URL%"
set "TRADEFRAME_FRONTEND_PORT=%FRONTEND_PORT%"
npm.cmd run dev -- --host 127.0.0.1 --port %FRONTEND_PORT%
