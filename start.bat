@echo off
cd /d "%~dp0"

python -c "import socket, sys; s=socket.socket(); res = s.connect_ex(('127.0.0.1', 88)); sys.exit(0 if res == 0 else 1)" > nul 2>&1
if errorlevel 1 (
    start "YJH-WebServer" /min python -X utf8 local_web/app.py
    timeout /t 3 /nobreak > nul
)

start "YJH-SupabaseBridge" /min python -X utf8 collector/supabase_bridge.py
explorer.exe "http://127.0.0.1:88/"
exit