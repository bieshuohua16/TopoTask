@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title TopoTash 拓事 · 首次启动
set "RC=1"

echo.
echo ============================================================
echo   TopoTash 拓事 - 首次启动
echo ============================================================
echo.

rem ---- 找到可用的 Python ----
set "PY_CMD="
python --version >nul 2>nul
if not errorlevel 1 set "PY_CMD=python"
if defined PY_CMD goto run_setup

py -3 --version >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"
if defined PY_CMD goto run_setup

echo [错误] 没有找到可用的 Python。
echo.
echo   请先从 https://www.python.org/downloads/ 安装 Python 3.10 或更高版本，
echo   安装时勾选 "Add python.exe to PATH"，然后重新双击本文件。
echo.
goto end

:run_setup
echo 使用 %PY_CMD% 运行首次启动向导 ...
echo.
%PY_CMD% "%~dp0setup_first_run.py" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo 首次启动向导已完成，可以双击桌面上的快捷方式启动 TopoTash。
) else (
  echo 首次启动向导未完成，请查看上面的错误信息后重试。
)

:end
echo.
pause
exit /b %RC%
