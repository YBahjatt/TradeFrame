@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "LOGS=%ROOT%\logs"
set "DATA=%ROOT%\data"
set "DB=%DATA%\tradeframe.sqlite3"

if not exist "%LOGS%" mkdir "%LOGS%"
if not exist "%DATA%" mkdir "%DATA%"

if exist "%LOGS%\backend.pid" (
  for /f "usebackq delims=" %%P in ("%LOGS%\backend.pid") do taskkill /PID %%P /F >nul 2>nul
  del "%LOGS%\backend.pid" >nul 2>nul
)
if exist "%LOGS%\frontend.pid" (
  for /f "usebackq delims=" %%P in ("%LOGS%\frontend.pid") do taskkill /PID %%P /F >nul 2>nul
  del "%LOGS%\frontend.pid" >nul 2>nul
)

if not exist "%DB%" (
  echo SQLite DB not found. Creating it from the current configured database...
  pushd "%BACKEND%"
  ".\.venv\Scripts\python.exe" "tools\migrate_to_sqlite.py"
  popd
)

for /f %%P in ('powershell -NoProfile -Command "$start=8000; for($p=$start;$p -lt $start+200;$p++){ if(-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)){ $p; break } }"') do set "BACKEND_PORT=%%P"
for /f %%P in ('powershell -NoProfile -Command "$start=5173; for($p=$start;$p -lt $start+200;$p++){ if(-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)){ $p; break } }"') do set "FRONTEND_PORT=%%P"

if "%BACKEND_PORT%"=="" (
  echo Could not find a free backend port near 8000.
  pause
  exit /b 1
)
if "%FRONTEND_PORT%"=="" (
  echo Could not find a free frontend port near 5173.
  pause
  exit /b 1
)

set "DB_URL=sqlite:///%DB:\=/%"
set "BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%"
set "FRONTEND_URL=http://127.0.0.1:%FRONTEND_PORT%/"

start "TradeFrame Backend" /min cmd /c call "%ROOT%\start-backend.bat" "%DB_URL%" "%BACKEND_PORT%" "%LOGS%"
start "TradeFrame Frontend" cmd /k call "%ROOT%\start-frontend.bat" "%BACKEND_URL%" "%FRONTEND_PORT%"

echo.
echo TradeFrame is starting.
echo.
echo Open this URL:
echo   %FRONTEND_URL%
echo.
echo Backend:
echo   %BACKEND_URL%
echo.
echo Database:
echo   %DB%
echo.
echo Logs:
echo   %LOGS%
echo.
echo Ports stay at 8000 and 5173 unless those ports are already in use.
echo.
pause
