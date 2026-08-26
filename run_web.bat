@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 裕珍皇 - Web 伺服器
python -X utf8 local_web/app.py
