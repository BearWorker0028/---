@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 裕珍皇冷鏈監控系統 - 建立桌面捷徑

echo =====================================================
echo   正在建立桌面捷徑 (圖示: 台菱牌 TL_logo)...
echo =====================================================
echo.

python -X utf8 "%~dp0scripts\make_desktop_shortcut.py"
if %errorlevel% equ 0 goto success

echo [提示] 正在使用備援機制建立桌面捷徑...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_shortcut.ps1"

:success
echo.
echo =====================================================
echo   [OK] 桌面捷徑建立成功！
echo   捷徑名稱: 裕珍皇 智慧冷鏈監控系統
echo   捷徑圖示: 台菱牌 (TL_logo)
echo =====================================================
echo.
echo 請按任意鍵關閉此視窗...
pause > nul
exit /b 0
