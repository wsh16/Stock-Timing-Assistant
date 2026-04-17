$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$startupScript = Join-Path $root "start_app.ps1"
$taskName = "TimingAssistantStartup"
$encodedCommand = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes("& `"$startupScript`"")
)
$taskRun = "powershell.exe -ExecutionPolicy Bypass -EncodedCommand $encodedCommand"
$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "TimingAssistantStartup.lnk"

function Install-StartupShortcut {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = '-ExecutionPolicy Bypass -File "' + $startupScript + '"'
    $shortcut.WorkingDirectory = $root
    $shortcut.WindowStyle = 7
    $shortcut.Save()
}

& schtasks.exe /Create `
    /TN $taskName `
    /TR $taskRun `
    /SC ONLOGON `
    /F | Out-Host

if ($LASTEXITCODE -eq 0) {
    Write-Host "Created Windows startup task: $taskName"
    exit 0
}

Install-StartupShortcut
if (-not (Test-Path $shortcutPath)) {
    throw "Failed to create Task Scheduler entry and failed to create Startup folder shortcut."
}

Write-Host "Task Scheduler creation failed. Fallback Startup shortcut created: $shortcutPath"
