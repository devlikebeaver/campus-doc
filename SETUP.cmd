@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
if errorlevel 1 (
  echo Setup failed. Copy the error above into your agent chat.
  pause
  exit /b 1
)
echo Setup and sample generation completed.
pause
