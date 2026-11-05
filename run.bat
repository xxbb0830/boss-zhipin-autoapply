@echo off
chcp 65001 >nul
title BOSS直聘 自动投递
cd /d "%~dp0scripts"

REM 本地覆盖（可选，不入库）：在里面设置 BOSS_PY / BOSS_ADB / BOSS_DATA
if exist "%~dp0config\env.local.cmd" call "%~dp0config\env.local.cmd"

set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" if defined BOSS_PY set PY=%BOSS_PY%
if not exist "%PY%" set PY=python

echo ============================================
echo  BOSS直聘 自动投递  (Ctrl+C to stop)
echo  参数原样传给 auto.py, 例如: run.bat --limit 20
echo ============================================
echo.

"%PY%" auto.py %*

echo.
echo ---- finished ----
pause
