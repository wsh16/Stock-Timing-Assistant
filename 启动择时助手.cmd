@echo off
setlocal

powershell.exe -ExecutionPolicy Bypass -File "%~dp0start_app.ps1"
if errorlevel 1 (
    echo.
    echo Failed to start the timing assistant.
    pause
)

endlocal
