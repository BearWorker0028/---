@echo off
chcp 65001 > nul
setlocal EnableExtensions
title 裕珍皇冷鏈監控系統 - 停止地端監控服務

echo =====================================================
echo    裕珍皇 智慧冷鏈監控系統 - 停止地端服務
echo =====================================================
echo.

echo 正在關閉地端監控進程 (Web Port 88 與 Modbus Reader)...
taskkill /F /FI "WINDOWTITLE eq 裕珍皇 - Web 伺服器*" > nul 2>&1
taskkill /F /FI "WINDOWTITLE eq 裕珍皇 - Modbus 採集器*" > nul 2>&1
taskkill /F /FI "WINDOWTITLE eq 裕珍皇 - 雲端橋接*" > nul 2>&1

echo.
echo ✅ 已成功停止所有監控服務！
echo.
timeout /t 3 > nul
