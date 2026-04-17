@echo off
setlocal

powershell.exe -ExecutionPolicy Bypass -File "%~dp0open_ui.ps1"
if errorlevel 1 (
    echo.
    echo Failed to open the timing assistant UI.
    pause
)

endlocal
