@echo off
setlocal
title DonatiPlan Kurulum

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"

if errorlevel 1 (
  echo.
  echo Kurulum tamamlanamadi. Yukaridaki hata mesajini kontrol edin.
  pause
  exit /b 1
)

echo.
echo DonatiPlan kurulumu tamamlandi.
pause
endlocal
