# -*- coding: utf-8 -*-
"""
一鍵將本地 SQLite (data/temperature.db) 的所有設定上傳至 Supabase 雲端

包含：
1. system_config (LINE Token, Target ID, Cooldown 等)
2. room_alarm_settings (各庫房高低溫門檻 Hi/Lo, 延遲, 補償)
"""

import os
import sys
import sqlite3
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
load_dotenv(os.path.join(ROOT_DIR, '.env'))

TZ_TW = timezone(timedelta(hours=8))

SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ 錯誤：.env 缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY")
    sys.exit(1)

try:
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
except ImportError:
    print("❌ 缺少 supabase 套件，請執行: pip install supabase")
    sys.exit(1)

def tw_now_str():
    return datetime.now(TZ_TW).strftime('%Y-%m-%d %H:%M:%S')

def sync():
    db_path = os.path.join(ROOT_DIR, 'data', 'temperature.db')
    if not os.path.exists(db_path):
        print(f"❌ 找不到本地資料庫: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print("=" * 60)
    print("🚀 開始將本地 SQLite 設定同步至 Supabase 雲端...")
    print(f"   目標 Supabase: {SUPABASE_URL}")
    print("=" * 60)

    # 1. 檢查並上傳 system_config
    sys_rows = c.execute("SELECT key, value FROM system_config").fetchall()
    print(f"\n[1/2] 讀取本地 system_config: 共 {len(sys_rows)} 筆設定")
    try:
        sys_payload = []
        for r in sys_rows:
            sys_payload.append({
                'key': r['key'],
                'value': str(r['value']),
                'updated_at': tw_now_str()
            })
        if sys_payload:
            sb.table('system_config').upsert(sys_payload).execute()
            print(f"  ✓ 成功上傳 {len(sys_payload)} 筆 system_config 至 Supabase：")
            for item in sys_payload:
                # 遮罩敏感 token
                v_display = item['value'][:15] + '...' if len(item['value']) > 20 else item['value']
                print(f"    - {item['key']}: {v_display}")
    except Exception as e:
        print(f"  ❌ 上傳 system_config 失敗: {e}")
        print("     提示：若顯示表不存在 (PGRST205)，請先至 Supabase SQL Editor 執行 database/supabase_system_and_alarm_config.sql")
        conn.close()
        return False

    # 2. 檢查並上傳 room_alarm_settings
    room_rows = c.execute("""
        SELECT room_id, name, channels, hi, lo, delay, alarm_enabled, temp_offset 
        FROM room_alarm_settings
    """).fetchall()
    print(f"\n[2/3] 讀取本地 room_alarm_settings: 共 {len(room_rows)} 個庫別")
    try:
        room_payload = []
        for r in room_rows:
            room_payload.append({
                'room_id': r['room_id'],
                'name': r['name'],
                'channels': r['channels'],
                'hi': r['hi'],
                'lo': r['lo'],
                'delay': r['delay'] if r['delay'] is not None else 10,
                'alarm_enabled': r['alarm_enabled'] if r['alarm_enabled'] is not None else 1,
                'temp_offset': r['temp_offset'] if r['temp_offset'] is not None else 0.0,
                'updated_at': tw_now_str()
            })
        if room_payload:
            sb.table('room_alarm_settings').upsert(room_payload).execute()
            print(f"  ✓ 成功上傳 {len(room_payload)} 筆 room_alarm_settings 至 Supabase：")
            for item in room_payload:
                print(f"    - [{item['room_id']}] {item['name']}: 上限 {item['hi']}°C, 下限 {item['lo']}°C, 延遲 {item['delay']}分, 啟用={bool(item['alarm_enabled'])}")
    except Exception as e:
        print(f"  ❌ 上傳 room_alarm_settings 失敗: {e}")
        print("     提示：若顯示表不存在 (PGRST205)，請先至 Supabase SQL Editor 執行 database/supabase_system_and_alarm_config.sql")
        conn.close()
        return False

    # 3. 檢查並上傳 alarm_settings (運轉電流閥值與 NFB 額定電流)
    alarm_rows = c.execute("""
        SELECT channel, name, hi, lo, delay, alarm_enabled, temp_offset, 
               current_threshold, nfb_rated_current, power_anomaly_threshold
        FROM alarm_settings
    """).fetchall()
    print(f"\n[3/3] 讀取本地 alarm_settings (運轉電流閥值): 共 {len(alarm_rows)} 個通道")
    try:
        alarm_payload = []
        for r in alarm_rows:
            alarm_payload.append({
                'channel': r['channel'],
                'name': r['name'],
                'hi': r['hi'],
                'lo': r['lo'],
                'delay': r['delay'] if r['delay'] is not None else 0,
                'alarm_enabled': r['alarm_enabled'] if r['alarm_enabled'] is not None else 1,
                'temp_offset': r['temp_offset'] if r['temp_offset'] is not None else 0.0,
                'current_threshold': r['current_threshold'] if r['current_threshold'] is not None else 0.5,
                'nfb_rated_current': r['nfb_rated_current'],
                'power_anomaly_threshold': r['power_anomaly_threshold'] if r['power_anomaly_threshold'] is not None else 15.0,
                'updated_at': tw_now_str()
            })
        if alarm_payload:
            sb.table('alarm_settings').upsert(alarm_payload).execute()
            print(f"  ✓ 成功上傳 {len(alarm_payload)} 筆 alarm_settings 至 Supabase：")
            for item in alarm_payload:
                print(f"    - [{item['channel']}] {item['name']}: 電流閥值={item['current_threshold']}A, NFB={item['nfb_rated_current']}A")
    except Exception as e:
        print(f"  ❌ 上傳 alarm_settings 失敗: {e}")
        print("     提示：若顯示表不存在 (PGRST205)，請先至 Supabase SQL Editor 執行 database/supabase_system_and_alarm_config.sql 增加 alarm_settings 表")
        conn.close()
        return False

    conn.close()
    print("\n" + "=" * 60)
    print("🎉 同步完成！Supabase 雲端目前已具備完整的系統、庫溫、以及運轉電流閥值設定！")
    print("=" * 60)
    return True

if __name__ == '__main__':
    sync()
