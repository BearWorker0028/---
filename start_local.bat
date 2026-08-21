@echo off
chcp 65001 > nul
setlocal EnableExtensions
title 裕珍皇冷鏈監控系統 - 案場地端正式版一鍵啟動

echo =====================================================
echo    裕珍皇 智慧冷鏈監控系統 - 案場地端正式版一鍵啟動
echo =====================================================
echo.
echo [1/3] 正在檢查 Python 執行環境...
python --version > nul 2>&1
if errorlevel 1 (
    echo [錯誤] 系統未偵測到 Python，請確認已安裝 Python 3.10+ 並勾選加入環境變數 PATH。
    pause
    exit /b 1
)

echo [2/3] 正在檢查必要套件 (Flask, Waitress, Pymodbus, OpenPyXL, Requests)...
python -c "import flask, waitress, pymodbus, openpyxl, requests" > nul 2>&1
if errorlevel 1 (
    echo [提示] 偵測到缺少必要套件，正在自動安裝...
    python -m pip install -r requirements.local.txt
)

echo [3/3] 正在啟動案場地端監控服務...
echo.

:: 1. 啟動地端 Web 電視牆伺服器 (Port 88, 內建 SQLite WAL / PostgreSQL 雙模引擎)
start "裕珍皇 - 地端 Web 伺服器 (Port 88)" cmd /k "chcp 65001 > nul & title 裕珍皇 - Web 伺服器 & python -X utf8 local_web/app.py"

:: 稍微等待後端就緒
timeout /t 2 /nobreak > nul

:: 2. 啟動地端 Modbus 採集器 (直連現場 W610 192.168.68.200:2000)
start "裕珍皇 - 地端 Modbus 採集器 (W610)" cmd /k "chcp 65001 > nul & title 裕珍皇 - Modbus 採集器 & python -X utf8 collector/modbus_reader.py"

echo =====================================================
echo   ✅ 案場地端監控所有服務啟動成功！
echo.
echo   👉 電視牆主畫面： http://127.0.0.1:88/
echo   👉 現場網關通訊： 192.168.68.200:2000 (W610)
echo.
echo   【操作提示】
echo   • 系統已開啟兩個核心服務視窗 (Web伺服器、Modbus直連採集)。
echo   • 即將自動為您開啟瀏覽器。
echo   • 若要結束監控，直接關閉該兩個服務視窗或執行 stop_local.bat。
echo =====================================================
echo.

timeout /t 2 /nobreak > nul
start "" "http://127.0.0.1:88/"

echo 按任意鍵關閉此引導視窗（背景監控將持續運行）...
pause > nul
