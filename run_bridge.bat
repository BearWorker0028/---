@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 裕珍皇 - Supabase 雲端橋接
python -X utf8 collector/supabase_bridge.py
