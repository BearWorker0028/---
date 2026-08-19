@echo off
chcp 65001 > nul
setlocal EnableExtensions
title 裕珍皇冷鏈監控系統 - 遠端監控一鍵啟動

echo =====================================================
echo    裕珍皇 智慧冷鏈監控系統 - 遠端監控一鍵啟動
echo =====================================================
echo.
echo [1/3] 正在檢查 Python 執行環境...
python --version > nul 2>&1
if errorlevel 1 (
    echo [錯誤] 系統未偵測到 Python，請確認已安裝 Python 3.10+ 並加入環境變數 PATH。
    pause
    exit /b 1
)

echo [2/3] 正在檢查必要套件 (Flask, Waitress, OpenPyXL, Supabase, Requests)...
python -c "import flask, waitress, openpyxl, supabase, requests" > nul 2>&1
if errorlevel 1 (
    echo [提示] 偵測到缺少必要套件，正在自動安裝...
    python -m pip install -r requirements.local.txt
)

echo [3/3] 正在啟動服務...
echo.

:: 1. 啟動本機 Web 電視牆伺服器 (Port 88)
start "裕珍皇 - 監控伺服器 (Web Port 88)" cmd /k "chcp 65001 > nul & title 裕珍皇 - Web 伺服器 & python -X utf8 local_web/app.py"

:: 稍微等待後端就緒
timeout /t 2 /nobreak > nul

:: 2. 啟動 Supabase 雲端資料橋接服務 (拉取即時讀值推入 Port 88)
start "裕珍皇 - 雲端數據橋接 (Supabase Bridge)" cmd /k "chcp 65001 > nul & title 裕珍皇 - 雲端橋接 & python -X utf8 collector/supabase_bridge.py"

echo =====================================================
echo   ✅ 遠端監控所有服務啟動成功！
echo.
echo   👉 電視牆主畫面： http://127.0.0.1:88/
echo   👉 遠端簡化畫面： http://127.0.0.1:88/remote
echo.
echo   【操作提示】
echo   • 系統已開啟兩個背景服務視窗 (Web伺服器、雲端橋接)。
echo   • 即將自動為您開啟瀏覽器。
echo   • 若要結束監控，直接關閉該兩個服務視窗即可。
echo =====================================================
echo.

timeout /t 2 /nobreak > nul
start "" "http://127.0.0.1:88/"

echo 按任意鍵關閉此引導視窗（背景監控將持續運行）...
pause > nul
