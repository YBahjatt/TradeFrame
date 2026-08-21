param([switch]$NoPause)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Logs = Join-Path $Root "logs"
$Data = Join-Path $Root "data"
$DbPath = Join-Path $Data "tradeframe.sqlite3"

function Find-FreePort {
    param([int]$StartPort)
    for ($port = $StartPort; $port -lt ($StartPort + 200); $port++) {
        $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $busy) { return $port }
    }
    throw "Could not find a free port near $StartPort."
}

function Stop-TradeFrameProcesses {
    foreach ($pidFile in @((Join-Path $Logs "backend.pid"), (Join-Path $Logs "frontend.pid"))) {
        if (-not (Test-Path $pidFile)) { continue }
        $processIdText = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        $processId = 0
        if (-not [int]::TryParse($processIdText, [ref]$processId)) { continue }
        try {
            Stop-Process -Id $processId -Force -ErrorAction Stop
        } catch {
            Write-Host "Could not stop previous TradeFrame process $($processId): $($_.Exception.Message)"
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path $DbPath)) {
    Write-Host "SQLite DB not found. Creating it from the current configured database..."
    Push-Location $Backend
    try {
        & ".\.venv\Scripts\python.exe" "tools\migrate_to_sqlite.py"
    } finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $Logs | Out-Null
Stop-TradeFrameProcesses
Start-Sleep -Milliseconds 500

$BackendPort = Find-FreePort 8000
$FrontendPort = Find-FreePort 5173
$Url = "http://127.0.0.1:$FrontendPort/"

$BackendOut = Join-Path $Logs "backend.out.log"
$BackendErr = Join-Path $Logs "backend.err.log"
$FrontendOut = Join-Path $Logs "frontend.out.log"
$FrontendErr = Join-Path $Logs "frontend.err.log"

$DatabaseUrl = "sqlite:///$($DbPath.Replace('\', '/'))"
$BackendCommand = "`$env:TRADEFRAME_DATABASE_URL='$DatabaseUrl'; Set-Location -LiteralPath '$Backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
$FrontendCommand = "set TRADEFRAME_BACKEND_URL=http://127.0.0.1:$BackendPort&& set TRADEFRAME_FRONTEND_PORT=$FrontendPort&& cd /d `"$Frontend`"&& npm.cmd run dev -- --host 127.0.0.1 --port $FrontendPort"

$BackendProcess = Start-Process -FilePath powershell -ArgumentList @("-NoProfile", "-Command", $BackendCommand) -WindowStyle Hidden -RedirectStandardOutput $BackendOut -RedirectStandardError $BackendErr -PassThru
$BackendProcess.Id | Set-Content (Join-Path $Logs "backend.pid")
Start-Sleep -Seconds 2
$FrontendProcess = Start-Process -FilePath cmd.exe -ArgumentList @("/k", $FrontendCommand) -PassThru
$FrontendProcess.Id | Set-Content (Join-Path $Logs "frontend.pid")
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "TradeFrame is starting."
Write-Host ""
Write-Host "Open this URL:"
Write-Host "  $Url"
Write-Host ""
Write-Host "Backend:"
Write-Host "  http://127.0.0.1:$BackendPort"
Write-Host ""
Write-Host "Database:"
Write-Host "  $DbPath"
Write-Host ""
Write-Host "Logs:"
Write-Host "  $Logs"
Write-Host ""
Write-Host "This window can be closed after you copy/open the URL."
if (-not $NoPause) {
    pause
}
