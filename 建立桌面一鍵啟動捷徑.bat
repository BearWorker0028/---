@echo off
chcp 65001 > nul
setlocal EnableExtensions
cd /d "%~dp0"
title 裕珍皇冷鏈監控系統 - 建立桌面捷徑

echo =====================================================
echo  正在為您在 Windows 桌面建立「裕珍皇冷鏈監控系統」一鍵捷徑...
echo =====================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "SHORTCUT_PATH=%DESKTOP_DIR%\裕珍皇 智慧冷鏈監控系統.lnk"
set "TARGET_BAT=%SCRIPT_DIR%start.bat"
set "ICON_PATH=%SCRIPT_DIR%local_web\static\YJH_logo.png"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$WshShell = New-Object -ComObject WScript.Shell; " ^
  "$Shortcut = $WshShell.CreateShortcut('%SHORTCUT_PATH%'); " ^
  "$Shortcut.TargetPath = '%TARGET_BAT%'; " ^
  "$Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; " ^
  "$Shortcut.Description = '裕珍皇 智慧冷鏈監控與能源管理系統 (一鍵開啟)'; " ^
  "$Shortcut.Save()"

if exist "%SHORTCUT_PATH%" (
    echo =====================================================
    echo  ✅ 桌面捷徑建立成功！
    echo.
    echo  桌面圖示名稱：【裕珍皇 智慧冷鏈監控系統】
    echo  業主日後只需在桌面點擊此捷徑，即可直接彈出滿版原生監控畫面！
    echo =====================================================
) else (
    echo [提示] 正在使用備援方式建立批次檔捷徑...
    copy "%SCRIPT_DIR%start.bat" "%DESKTOP_DIR%\裕珍皇 智慧冷鏈監控系統.bat" > nul
    echo  ✅ 已在桌面建立啟動批次檔！
)

echo.
echo 請按任意鍵關閉此視窗...
pause > nul
