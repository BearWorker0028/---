@echo off
chcp 65001 > nul
setlocal EnableExtensions
title 裕珍皇冷鏈監控系統 - 設定 Windows 開機自動常駐

echo =====================================================
echo    裕珍皇 智慧冷鏈監控系統 - 設定開機自動常駐啟動
echo =====================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\YJH_SCADA_AutoStart.vbs"

echo 正在建立開機常駐捷徑至: %STARTUP_FOLDER%
echo.

(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.CurrentDirectory = "%SCRIPT_DIR%"
echo WshShell.Run "cmd /c start_local.bat", 1, False
) > "%SHORTCUT_PATH%"

if exist "%SHORTCUT_PATH%" (
    echo =====================================================
    echo   ✅ 成功設定開機自動啟動！
    echo   • 每次電腦重開機或跳電復電後，系統將自動拉起監控服務。
    echo =====================================================
) else (
    echo [錯誤] 無法建立開機啟動檔，請以系統管理員身分執行此批次檔。
)

echo.
pause
