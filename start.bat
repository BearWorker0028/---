@echo off
chcp 65001 > nul
title 裕珍皇中央監控系統 - 本地測試伺服器
echo =====================================================
echo    裕珍皇 中央監控電視牆 - 本地測試啟動腳本
echo =====================================================
echo.
echo [1/2] 正在檢查 Python 執行環境...
python --version > nul 2>&1
if errorlevel 1 (
    echo [錯誤] 系統未偵測到 Python，請先安裝 Python 並將其加入 PATH 中。
    pause
    exit /b 1
)

echo [2/2] 正在以 UTF-8 模式啟動網頁監控伺服器 (包含模擬數據)...
echo.
echo =====================================================
echo   伺服器啟動成功！請打開瀏覽器造訪以下網址：
echo   👉 http://127.0.0.1:88/
echo   👉 http://127.0.0.1:88/remote  (遠端畫面)
echo =====================================================
echo.
python -X utf8 local_web/app.py
pause
