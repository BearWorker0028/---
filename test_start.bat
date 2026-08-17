@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist "local_web\test_start_local.bat" (
    echo Cannot find local_web\test_start_local.bat
    echo.
    pause
    exit /b 1
)

cmd /k call "%~dp0local_web\test_start_local.bat"
