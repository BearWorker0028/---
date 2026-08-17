@echo off
chcp 65001 > nul
title 裕珍皇中央監控系統 - 一鍵啟動 (含夜間資料記錄)
echo =====================================================
echo    裕珍皇 中央監控系統 - 一鍵啟動 (含夜間資料記錄)
echo =====================================================
echo.
echo [1/3] 正在檢查 Python 執行環境...
python --version > nul 2>&1
if errorlevel 1 (
    echo [錯誤] 系統未偵測到 Python，請先確認已安裝 Python 並加入環境變數 PATH。
    pause
    exit /b 1
)

echo [2/3] 正在啟動本機監控後端伺服器 (Port 88)...
start "裕珍皇 - 監控伺服器 (local_web)" cmd /k "chcp 65001 > nul & python -X utf8 local_web/app.py"

timeout /t 3 /nobreak > nul

echo [3/3] 正在啟動 Supabase 雲端資料橋接與夜間記錄服務...
start "裕珍皇 - 雲端資料橋接 (每分鐘存入DB)" cmd /k "chcp 65001 > nul & python -X utf8 collector/supabase_bridge.py"

echo.
echo =====================================================
echo   所有服務啟動成功！
echo   👉 監控畫面： http://127.0.0.1:88/
echo   👉 遠端畫面： http://127.0.0.1:88/remote
echo.
echo   【夜間掛機記錄注意事項】
echo   請保持上述開啟的視窗運行，系統將每分鐘持續記錄數據至資料庫。
echo =====================================================
echo.

timeout /t 2 /nobreak > nul
start "" "http://127.0.0.1:88/"

echo 按任意鍵關閉此引導視窗（背景服務將持續在各自視窗中運行）...
pause > nul
