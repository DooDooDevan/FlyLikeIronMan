@echo off
title Fly Like Iron Man
set "FLIM=%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PATH=%FLIM%runtime\python;%PATH%"
if not exist "%FLIM%runtime\python\python.exe" (
  echo The runtime folder is missing. Unzip the whole download again, keeping all folders.
  pause
  exit /b 1
)
pushd "%FLIM%app"
"%FLIM%runtime\python\python.exe" -u start_flight.py %*
echo.
pause
