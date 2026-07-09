@echo off
setlocal
title DonatiPlan Baslatici

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1"

if errorlevel 1 (
  echo.
  echo DonatiPlan baslatilamadi. Yukaridaki hata mesajini kontrol edin.
  pause
)

endlocal
