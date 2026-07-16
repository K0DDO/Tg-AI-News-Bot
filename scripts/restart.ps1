# Briefly - stop old bot/worker/api and start fresh.
# Usage:
#   .\scripts\restart.ps1
#   .\scripts\restart.ps1 -SkipMigrate
#   .\scripts\restart.ps1 -NoApi
#   double-click scripts\restart.bat

param(
    [switch]$SkipMigrate,
    [switch]$NoApi,
    [switch]$NoWorker,
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"

if ($PSScriptRoot) {
    $Root = Split-Path -Parent $PSScriptRoot
} else {
    $Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
Set-Location -LiteralPath $Root

# Prefer .env.production (server config); optional explicit override via BRIEFLY_ENV_FILE
if (-not $env:BRIEFLY_ENV_FILE -and (Test-Path -LiteralPath (Join-Path $Root ".env.production"))) {
    $env:BRIEFLY_ENV_FILE = (Join-Path $Root ".env.production")
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "ERROR: .venv not found:" -ForegroundColor Red
    Write-Host "  $Python"
    Write-Host "Run: python -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$LogDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Get-BrieflyPython {
    # Only top-level processes (parent is not another briefly python).
    # Worker/bot may spawn child pythons that share the same CommandLine.
    $all = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match 'app\.bot\.main' -or
                $_.CommandLine -match 'app\.tasks\.worker' -or
                $_.CommandLine -match 'app\.runtime' -or
                $_.CommandLine -match 'uvicorn.*app\.api\.main'
            )
        })
    $byPid = @{}
    foreach ($p in $all) { $byPid[$p.ProcessId] = $p }
    $all | Where-Object {
        -not $byPid.ContainsKey($_.ParentProcessId)
    }
}

function Stop-BrieflyProcesses {
    Write-Host ""
    Write-Host "[1/3] Stopping previous Briefly processes..." -ForegroundColor Cyan
    $killed = 0
    foreach ($p in @(Get-BrieflyPython)) {
        try {
            Write-Host "  kill PID $($p.ProcessId)"
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            $killed++
        } catch {
            Write-Host "  warn: could not kill PID $($p.ProcessId)" -ForegroundColor Yellow
        }
    }

    try {
        foreach ($l in @(Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue)) {
            $ownerPid = $l.OwningProcess
            if (-not $ownerPid) { continue }
            $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction SilentlyContinue
            if ($owner -and $owner.CommandLine -match "uvicorn|app\.api") {
                Write-Host "  kill PID $ownerPid (port $ApiPort)"
                Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
                $killed++
            }
        }
    } catch { }

    Start-Sleep -Seconds 2
    foreach ($p in @(Get-BrieflyPython)) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        $killed++
    }
    Start-Sleep -Seconds 1
    Write-Host "  stopped: $killed process(es)"
}

function Start-BrieflyProcess {
    param(
        [string]$Name,
        [string]$PyArgs,
        [string]$LogFile
    )
    $logPath = Join-Path $LogDir $LogFile
    $safeName = ($Name -replace '\s', '_')
    $wrapper = Join-Path $LogDir ("start_{0}.cmd" -f $safeName)

    # Visible console + UTF-8. Output stays in the window (easy to debug).
    $content = @"
@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Briefly - $Name
cd /d "$Root"
echo [%date% %time%] starting $Name
"$Python" $PyArgs
echo.
echo $Name stopped (exit %ERRORLEVEL%).
echo Log dir: $LogDir
pause
"@
    Set-Content -LiteralPath $wrapper -Value $content -Encoding ASCII

    # Start the .cmd directly - opens its own console (no nested Start-Process quirks)
    Start-Process -FilePath $wrapper -WorkingDirectory $Root | Out-Null
    Write-Host "  started $Name (console window)"
}

Write-Host "Briefly restart" -ForegroundColor Cyan
Write-Host "  root:   $Root"
Write-Host "  python: $Python"

Stop-BrieflyProcesses

if (-not $SkipMigrate) {
    Write-Host ""
    Write-Host "[2/3] alembic upgrade head..." -ForegroundColor Cyan
    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: migration failed" -ForegroundColor Red
        exit $LASTEXITCODE
    }
} else {
    Write-Host ""
    Write-Host "[2/3] skip migrations" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[3/3] Starting stack..." -ForegroundColor Cyan

if (-not $NoApi) {
    Start-BrieflyProcess -Name "API" -PyArgs "-m uvicorn app.api.main:app --host 127.0.0.1 --port $ApiPort" -LogFile "api.log"
}
if (-not $NoWorker) {
    Start-BrieflyProcess -Name "Worker" -PyArgs "-m app.tasks.worker" -LogFile "worker.log"
}
Start-BrieflyProcess -Name "Bot" -PyArgs "-m app.bot.main" -LogFile "bot.log"

Start-Sleep -Seconds 5

$running = @(Get-BrieflyPython)
Write-Host ""
if ($running.Count -eq 0) {
    Write-Host "WARNING: no python processes detected. Look at the opened console windows." -ForegroundColor Yellow
} else {
    Write-Host "Done. Running:" -ForegroundColor Green
    foreach ($p in $running) {
        $snippet = $p.CommandLine.Substring(0, [Math]::Min(110, $p.CommandLine.Length))
        Write-Host ("  PID {0}: {1}" -f $p.ProcessId, $snippet)
    }
}
Write-Host "Logs dir: $LogDir"
Write-Host "API: http://127.0.0.1:$ApiPort"
Write-Host "Console windows should stay open for Bot / Worker / API"
