@echo off
chcp 65001 > nul
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
set "DATA_ROOT=%~dp0local_web_0624"
set "DB_DIR=%~dp0local_web_0624\data"
set "MAIN_DB_PATH=%~dp0local_web_0624\temperature.db"
set "MOCK_DATA_ENABLED=true"
set "PUBLISH_TO_API=0"
cd /d "%~dp0local_web_0624"
"%PYTHON_EXE%" -X utf8 app.py
pause
