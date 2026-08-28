# -*- coding: utf-8 -*-
import os
import sys
import sqlite3
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

print('=== 1. 檢查 Supabase 上的 GW2 狀態 ===')
try:
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 檢查網關診斷表
    gw_res = sb.table('gateway_status').select('*').execute()
    print('Gateway Status:')
    for row in gw_res.data:
        print(f"  {row.get('gateway_id')}: online={row.get('is_online')} ip={row.get('client_ip')} updated={row.get('updated_at')}")
        
    # 檢查 GW2 溫度表
    t_res = sb.table('gw2_temp_status').select('channel, device_name, control_temp, updated_at').execute()
    print('\nGW2 溫度狀態 (gw2_temp_status):')
    for row in t_res.data:
        print(f"  {row.get('channel')}: {row.get('device_name')} = {row.get('control_temp')} °C (更新: {row.get('updated_at')})")
        
    # 檢查 GW2 電錶表
    m_res = sb.table('gw2_meter_status').select('channel, device_name, voltage_avg, current_avg, power_total, energy_total, updated_at').execute()
    print('\nGW2 電錶狀態 (gw2_meter_status):')
    for row in m_res.data:
        print(f"  {row.get('channel')}: {row.get('device_name')} | V_avg={row.get('voltage_avg')}V, A_avg={row.get('current_avg')}A, kW={row.get('power_total')}, kWh={row.get('energy_total')} (更新: {row.get('updated_at')})")

    # 檢查設備狀態表
    d_res = sb.table('device_status').select('channel, device_name, is_online, updated_at').execute()
    print('\n設備狀態 (device_status):')
    for row in d_res.data:
        print(f"  {row.get('channel')}: {row.get('device_name')} | online={row.get('is_online')} (更新: {row.get('updated_at')})")

except Exception as e:
    print('Supabase 查詢錯誤:', e)

print('\n=== 2. 檢查本地 SQLite (data/temperature.db) ===')
db_path = os.path.join('data', 'temperature.db')
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 檢查 power_readings 筆數與最新記錄
    for ch in ['ch13', 'ch14']:
        cnt = c.execute('SELECT COUNT(*) FROM power_readings WHERE channel=?', (ch,)).fetchone()[0]
        latest = c.execute('SELECT timestamp, v, a, kw, pf, kwh FROM power_readings WHERE channel=? ORDER BY timestamp DESC LIMIT 1', (ch,)).fetchone()
        print(f'power_readings {ch}: 總計 {cnt} 筆 | 最新: {latest}')
        
    # 檢查 temperatures 最新記錄
    for ch in ['ch08', 'ch09', 'ch10', 'ch11', 'ch12', 'ch13', 'ch14']:
        cnt = c.execute('SELECT COUNT(*) FROM temperatures WHERE channel=?', (ch,)).fetchone()[0]
        latest = c.execute('SELECT timestamp, name, value, status FROM temperatures WHERE channel=? ORDER BY timestamp DESC LIMIT 1', (ch,)).fetchone()
        print(f'temperatures {ch}: 總計 {cnt} 筆 | 最新: {latest}')
    conn.close()
else:
    print(f'找不到本地資料庫: {db_path}')
