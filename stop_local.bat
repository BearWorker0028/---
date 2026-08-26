@echo off
chcp 65001 > nul
setlocal EnableExtensions
title 裕珍皇冷鏈監控系統 - 停止所有服務

echo =====================================================
echo  正在停止 裕珍皇 監控相關服務...
echo =====================================================
echo.

taskkill /F /FI "WINDOWTITLE eq 裕珍皇*" > nul 2>&1
taskkill /F /FI "WINDOWTITLE eq YJH-*" > nul 2>&1

echo [OK] 所有服務已成功停止。
timeout /t 2 > nul