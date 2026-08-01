@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
echo ============================================================
echo   Meeting Action Extractor - Startup
echo ============================================================
echo.

cd /d "%~dp0"

REM Use sandbox Python if available
set "SANDBOX_PY=C:\Users\lenovo\AppData\Roaming\qianfan-desktop-app\lightsandbox\python\python.exe"

if exist "!SANDBOX_PY!" (
    set "PY_CMD=!SANDBOX_PY!"
    echo [INFO] Using sandbox Python
) else (
    set "PY_CMD=python"
    echo [INFO] Using system Python
)

!PY_CMD! --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

!PY_CMD! --version

echo.
echo [Checking dependencies]...
!PY_CMD! -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [Installing dependencies]...
    !PY_CMD! -m pip install flask openai pandas openpyxl -i https://mirrors.aliyun.com/pypi/simple/
)

echo.
echo ============================================================
echo   Server running at: http://127.0.0.1:5000
echo   Press Ctrl+C to stop
echo ============================================================
echo.

!PY_CMD! app.py
pause
endlocal
