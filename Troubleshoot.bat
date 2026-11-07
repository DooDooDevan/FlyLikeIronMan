@echo off
title Fly Like Iron Man - check setup
set "FLIM=%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
pushd "%FLIM%app"
"%FLIM%runtime\python\python.exe" flim_paths.py
echo.
"%FLIM%runtime\python\python.exe" version_check.py
echo.
"%FLIM%runtime\python\python.exe" setup_mod.py status
echo.
"%FLIM%runtime\python\python.exe" start_flight.py --dry-run
echo.
"%FLIM%runtime\python\python.exe" report.py
echo.
echo (For a bug report: attach the file app\report.txt, or copy this window's text.)
pause
