@echo off
chcp 65001 > nul
pushd "%~dp0"
title YJH-Modbus-Reader
python -X utf8 collector\modbus_reader.py
