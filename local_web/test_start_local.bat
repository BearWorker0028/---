@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"

set "WEB_ROOT=%CD%"
set "PROJECT_ROOT=%WEB_ROOT%\.."
set "LOG_FILE=%WEB_ROOT%\test_start.log"
echo [%date% %time%] local test launcher started > "%LOG_FILE%"

echo =====================================================
echo YJH local web test launcher
echo =====================================================
echo.
echo This test launcher runs from the local_web folder.
echo Modbus reader is NOT started.
echo Mock data is enabled.
echo Log file:
echo %LOG_FILE%
echo.

set "PYTHON_EXE="

if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if defined PYTHON_EXE goto python_found

where py > nul 2>&1
if errorlevel 1 goto try_python
set "PYTHON_EXE=py -3"
goto python_found

:try_python
where python > nul 2>&1
if errorlevel 1 goto try_codex_python
set "PYTHON_EXE=python"
goto python_found

:try_codex_python
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if defined PYTHON_EXE goto python_found

echo ERROR: Python was not found.
echo ERROR: Python was not found.>> "%LOG_FILE%"
echo.
pause
exit /b 1

:python_found
echo Python command: %PYTHON_EXE%
echo Python command: %PYTHON_EXE%>> "%LOG_FILE%"
%PYTHON_EXE% --version
%PYTHON_EXE% --version>> "%LOG_FILE%" 2>&1
if errorlevel 1 goto python_failed

echo.
echo Checking Python packages...
%PYTHON_EXE% -X utf8 -c "import flask, waitress, openpyxl; print('dependencies ok')">> "%LOG_FILE%" 2>&1
if errorlevel 1 goto install_packages
goto packages_ok

:install_packages
echo Missing packages. Installing from ..\requirements.local.txt ...
echo Installing packages...>> "%LOG_FILE%"
%PYTHON_EXE% -m pip install -r "%PROJECT_ROOT%\requirements.local.txt">> "%LOG_FILE%" 2>&1
if errorlevel 1 goto package_failed

%PYTHON_EXE% -X utf8 -c "import flask, waitress, openpyxl; print('dependencies ok')">> "%LOG_FILE%" 2>&1
if errorlevel 1 goto package_failed

:packages_ok
echo Package check OK.

set "API_BASE=http://127.0.0.1:88"
set "DATA_ROOT=%CD%"
set "DB_DIR=%CD%\data"
set "MAIN_DB_PATH=%CD%\temperature.db"
set "MOCK_DATA_ENABLED=true"
set "PUBLISH_TO_API=0"
set "DATABASE_URL="

echo.
echo Checking port 88...
netstat -ano | findstr /R /C:":88 .*LISTENING" > nul 2>&1
if not errorlevel 1 goto port_busy

echo.
echo =====================================================
echo Starting server...
echo Open: http://127.0.0.1:88/
echo Remote: http://127.0.0.1:88/remote
echo.
echo Keep this window open. Press Ctrl+C to stop.
echo =====================================================
echo.
echo Browser will open automatically in a few seconds...
start "" /min cmd /c "timeout /t 3 /nobreak > nul & start "" "http://127.0.0.1:88/""
echo Starting app.py>> "%LOG_FILE%"
%PYTHON_EXE% -X utf8 app.py>> "%LOG_FILE%" 2>&1
goto server_stopped

:python_failed
echo ERROR: Python command failed.
echo ERROR: Python command failed.>> "%LOG_FILE%"
goto end_fail

:package_failed
echo ERROR: Python packages could not be installed or imported.
echo See log:
echo %LOG_FILE%
goto end_fail

:port_busy
echo ERROR: Port 88 is already in use.
echo ERROR: Port 88 is already in use.>> "%LOG_FILE%"
goto end_fail

:server_stopped
echo.
echo Server stopped. Exit code: %ERRORLEVEL%
echo Server stopped. Exit code: %ERRORLEVEL%>> "%LOG_FILE%"
echo See log:
echo %LOG_FILE%
goto end_fail

:end_fail
echo.
pause
exit /b 1
