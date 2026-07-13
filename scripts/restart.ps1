# Briefly — stop old bot/worker/api processes and start the stack fresh.
# Usage (from project root):
#   .\scripts\restart.ps1
#   .\scripts\restart.ps1 -SkipMigrate
#   .\scripts\restart.ps1 -NoApi

param(
    [switch]$SkipMigrate,
    [switch]$NoApi,
    [switch]$NoWorker,
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: .venv not found. Run: python -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

$LogDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Get-BrieflyPython {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match 'app\.bot\.main' -or
                $_.CommandLine -match 'app\.tasks\.worker' -or
                $_.CommandLine -match 'uvicorn.*app\.api\.main'
            )
        }
}

function Stop-BrieflyProcesses {
    Write-Host "`n[1/3] Stopping previous Briefly processes..." -ForegroundColor Cyan
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
        $listeners = Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue
        foreach ($l in $listeners) {
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
    # second pass
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
        [string]$Arguments,
        [string]$LogFile
    )
    $logPath = Join-Path $LogDir $LogFile
    # Single python process; append stdout/stderr to log (no Tee double-pipe quirks)
    $psCmd = @"
`$Host.UI.RawUI.WindowTitle = 'Briefly · $Name'
Set-Location -LiteralPath '$Root'
`$ErrorActionPreference = 'Continue'
& '$Python' $Arguments *>> '$logPath'
"@
    Start-Process -FilePath "powershell.exe" -WorkingDirectory $Root -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $psCmd
    ) | Out-Null
    Write-Host "  started $Name → $logPath"
}

function Keep-One {
    param([string]$Pattern, [string]$Label)
    $list = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -match $Pattern } |
        Sort-Object ProcessId)
    if ($list.Count -le 1) { return }
    $keep = $list[-1]
    foreach ($p in $list[0..($list.Count - 2)]) {
        Write-Host "  dedupe ${Label}: kill $($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  dedupe ${Label}: keep $($keep.ProcessId)"
}

Stop-BrieflyProcesses

if (-not $SkipMigrate) {
    Write-Host "`n[2/3] alembic upgrade head..." -ForegroundColor Cyan
    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: migration failed" -ForegroundColor Red
        exit $LASTEXITCODE
    }
} else {
    Write-Host "`n[2/3] skip migrations" -ForegroundColor Yellow
}

Write-Host "`n[3/3] Starting stack..." -ForegroundColor Cyan

if (-not $NoApi) {
    Start-BrieflyProcess -Name "API" -Arguments "-m uvicorn app.api.main:app --host 127.0.0.1 --port $ApiPort" -LogFile "api.log"
}
if (-not $NoWorker) {
    Start-BrieflyProcess -Name "Worker" -Arguments "-m app.tasks.worker" -LogFile "worker.log"
}
Start-BrieflyProcess -Name "Bot" -Arguments "-m app.bot.main" -LogFile "bot.log"

Start-Sleep -Seconds 3
Keep-One 'app\.bot\.main' 'bot'
Keep-One 'app\.tasks\.worker' 'worker'
Keep-One 'uvicorn.*app\.api\.main' 'api'

Write-Host "`nDone. Opened separate windows: Bot / Worker / API" -ForegroundColor Green
Write-Host "Logs: $LogDir"
Write-Host "API: http://127.0.0.1:$ApiPort"
Get-BrieflyPython | ForEach-Object {
    Write-Host ("  PID {0}: {1}" -f $_.ProcessId, $_.CommandLine.Substring(0, [Math]::Min(90, $_.CommandLine.Length)))
}
