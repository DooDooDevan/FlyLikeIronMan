@echo off
title Uninstall Fly Like Iron Man
set "FLIM=%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
pushd "%FLIM%app"
echo This removes the Fly Like Iron Man files from your No Man's Sky folder.
echo Close No Man's Sky first.
echo.
choice /C YN /M "Remove them now"
if errorlevel 2 exit /b 0
"%FLIM%runtime\python\python.exe" setup_mod.py uninstall
echo.
echo Done. You can now delete this folder:
echo   "%FLIM%"
pause
