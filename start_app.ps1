$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$appScript = Join-Path $root "app.py"
$workerScript = Join-Path $root "worker.py"
$heartbeatAgeSeconds = 180

if (-not (Test-Path $python)) {
    throw "未找到虚拟环境解释器: $python"
}

$workerHeartbeatState = "unknown"
try {
    $workerHeartbeatCode = @'
from datetime import datetime, timezone
from timing_assistant.database import get_settings

value = get_settings().get('worker_last_heartbeat', '').strip()
if not value:
    print('missing')
else:
    heartbeat = datetime.fromisoformat(value)
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - heartbeat.astimezone(timezone.utc)).total_seconds()
    print('stale' if age > __MAX_AGE__ else 'fresh')
'@
    $workerHeartbeatCode = $workerHeartbeatCode.Replace("__MAX_AGE__", "$heartbeatAgeSeconds")
    $workerHeartbeatState = (& $python -c $workerHeartbeatCode).Trim()
} catch {
    $workerHeartbeatState = "unknown"
}

$workerRunning = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*worker.py*" -and $_.ExecutablePath -eq $python }

if ($workerRunning -and $workerHeartbeatState -eq "stale") {
    $workerRunning | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    $workerRunning = $null
}

if (-not $workerRunning) {
    Start-Process `
        -FilePath $python `
        -ArgumentList ('"' + $workerScript + '"') `
        -WorkingDirectory $root `
        -WindowStyle Minimized | Out-Null
}

$streamlitRunning = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*streamlit*app.py*" -and $_.ExecutablePath -eq $python }

if (-not $streamlitRunning) {
    Start-Process `
        -FilePath $python `
        -ArgumentList @(
            "-m",
            "streamlit",
            "run",
            ('"' + $appScript + '"'),
            "--server.port",
            "8501",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false"
        ) `
        -WorkingDirectory $root `
        -WindowStyle Minimized | Out-Null
}

Write-Host "Timing assistant started."
Write-Host "UI: http://localhost:8501"
