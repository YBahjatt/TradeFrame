@echo off
setlocal
set "DB_URL=%~1"
set "BACKEND_PORT=%~2"
set "LOGS=%~3"
cd /d "%~dp0backend"
set "TRADEFRAME_DATABASE_URL=%DB_URL%"
".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% > "%LOGS%\backend.out.log" 2> "%LOGS%\backend.err.log"
