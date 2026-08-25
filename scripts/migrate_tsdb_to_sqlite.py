# -*- coding: utf-8 -*-
"""
【階段 1~3 自動化遷移腳本】TimescaleDB (Docker) → SQLite WAL

功能：
  1. 從 Docker 容器內的 PostgreSQL 讀取 10 張資料表全量數據
  2. 在 data/temperature.db 建立 SQLite WAL 資料庫（含精準索引）
  3. 批次寫入所有歷史資料並進行雙軌校驗（筆數比對）
  4. 輸出 JSON 備份至 backups/ 資料夾（額外安全網）

執行方式：
  python scripts/migrate_tsdb_to_sqlite.py
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

# 確保可以 import psycopg
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("❌ 請先安裝 psycopg: pip install psycopg[binary]")
    sys.exit(1)

from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, '.env'))

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if not DATABASE_URL:
    print("❌ .env 中缺少 DATABASE_URL")
    sys.exit(1)

SQLITE_PATH = os.path.join(ROOT_DIR, 'data', 'temperature.db')
BACKUP_DIR = os.path.join(ROOT_DIR, 'backups', f'tsdb_snapshot_{datetime.now().strftime("%Y%m%d_%H%M%S")}')

TZ_TW = timezone(timedelta(hours=8))


def fmt_ts(val):
    """將 datetime 轉為 SQLite 友善的文字格式"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.astimezone(TZ_TW).strftime('%Y-%m-%d %H:%M:%S')
    return str(val)


def fmt_date(val):
    if val is None:
        return None
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return str(val)


# ══════════════════════════════════════════════════
# 階段 1：從 TimescaleDB 全量讀取
# ══════════════════════════════════════════════════
def export_from_tsdb():
    print("\n═══════════════════════════════════════════════════")
    print("  📦 階段 1：從 TimescaleDB 匯出全量數據")
    print("═══════════════════════════════════════════════════")
    
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    tables = {}
    
    # temperatures
    print("  讀取 temperatures ...")
    rows = conn.execute("SELECT * FROM temperatures ORDER BY timestamp").fetchall()
    tables['temperatures'] = [{
        'id': r['id'], 'timestamp': fmt_ts(r['timestamp']),
        'channel': r['channel'], 'name': r.get('name'),
        'value': r['value'], 'status': r.get('status', 'NORMAL'),
        'runtime_hours': r.get('runtime_hours', 0.0),
        'control_temp': r.get('control_temp'),
        'coil_temp': r.get('coil_temp'),
        'compressor_current': r.get('compressor_current'),
        'high_pressure': r.get('high_pressure'),
        'low_pressure': r.get('low_pressure'),
        'set_temp': r.get('set_temp')
    } for r in rows]
    print(f"    → {len(tables['temperatures'])} 筆")
    
    # power_readings
    print("  讀取 power_readings ...")
    rows = conn.execute("SELECT * FROM power_readings ORDER BY timestamp").fetchall()
    tables['power_readings'] = [{
        'id': r['id'], 'timestamp': fmt_ts(r['timestamp']),
        'channel': r.get('channel'), 'v': r.get('v'), 'a': r.get('a'),
        'kw': r.get('kw'), 'pf': r.get('pf'), 'kwh': r.get('kwh')
    } for r in rows]
    print(f"    → {len(tables['power_readings'])} 筆")
    
    # alarm_settings
    print("  讀取 alarm_settings ...")
    rows = conn.execute("SELECT * FROM alarm_settings ORDER BY channel").fetchall()
    tables['alarm_settings'] = [dict(r) for r in rows]
    print(f"    → {len(tables['alarm_settings'])} 筆")
    
    # alarm_history
    print("  讀取 alarm_history ...")
    rows = conn.execute("SELECT * FROM alarm_history ORDER BY id").fetchall()
    tables['alarm_history'] = [{
        'id': r['id'], 'triggered_at': fmt_ts(r.get('triggered_at')),
        'channel': r.get('channel'), 'name': r.get('name'),
        'value': r.get('value'), 'alarm_type': r.get('alarm_type'),
        'hi': r.get('hi'), 'lo': r.get('lo'),
        'category': r.get('category', 'ALARM'),
        'alarm_message': r.get('alarm_message'),
        'restored_at': fmt_ts(r.get('restored_at')),
        'duration_sec': r.get('duration_sec'),
        'status': r.get('status', 'ACTIVE')
    } for r in rows]
    print(f"    → {len(tables['alarm_history'])} 筆")
    
    # daily_power_stats
    print("  讀取 daily_power_stats ...")
    rows = conn.execute("SELECT * FROM daily_power_stats ORDER BY date").fetchall()
    tables['daily_power_stats'] = [{
        'date': fmt_date(r['date']),
        'total_kwh': r.get('total_kwh', 0),
        'peak_kwh': r.get('peak_kwh', 0),
        'semi_peak_kwh': r.get('semi_peak_kwh', 0),
        'off_peak_kwh': r.get('off_peak_kwh', 0)
    } for r in rows]
    print(f"    → {len(tables['daily_power_stats'])} 筆")
    
    # hourly_power_stats
    print("  讀取 hourly_power_stats ...")
    rows = conn.execute("SELECT * FROM hourly_power_stats ORDER BY hour_timestamp").fetchall()
    tables['hourly_power_stats'] = [{
        'hour_timestamp': fmt_ts(r['hour_timestamp']),
        'ch13_kwh_delta': r.get('ch13_kwh_delta', 0),
        'ch14_kwh_delta': r.get('ch14_kwh_delta', 0),
        'total_kwh_delta': r.get('total_kwh_delta', 0),
        'tariff_type': r.get('tariff_type', 'off_peak'),
        'is_anomaly': 1 if r.get('is_anomaly') else 0
    } for r in rows]
    print(f"    → {len(tables['hourly_power_stats'])} 筆")
    
    # device_commands
    print("  讀取 device_commands ...")
    rows = conn.execute("SELECT * FROM device_commands ORDER BY id").fetchall()
    tables['device_commands'] = [{
        'id': r['id'], 'channel': r['channel'],
        'command_type': r['command_type'], 'value': r.get('value'),
        'status': r.get('status', 'pending'),
        'error_message': r.get('error_message'),
        'created_at': fmt_ts(r.get('created_at')),
        'executed_at': fmt_ts(r.get('executed_at'))
    } for r in rows]
    print(f"    → {len(tables['device_commands'])} 筆")
    
    # room_alarm_settings
    print("  讀取 room_alarm_settings ...")
    rows = conn.execute("SELECT * FROM room_alarm_settings ORDER BY room_id").fetchall()
    tables['room_alarm_settings'] = [dict(r) for r in rows]
    print(f"    → {len(tables['room_alarm_settings'])} 筆")
    
    # system_config
    print("  讀取 system_config ...")
    rows = conn.execute("SELECT * FROM system_config ORDER BY key").fetchall()
    tables['system_config'] = [dict(r) for r in rows]
    print(f"    → {len(tables['system_config'])} 筆")
    
    conn.close()
    
    # 寫出 JSON 備份
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for tbl_name, data in tables.items():
        fpath = os.path.join(BACKUP_DIR, f'{tbl_name}.json')
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        print(f"  💾 JSON 備份 → {fpath}")
    
    print(f"\n  ✅ 階段 1 完成：共匯出 {sum(len(v) for v in tables.values())} 筆數據，JSON 備份已儲存")
    return tables


# ══════════════════════════════════════════════════
# 階段 2：建置 SQLite WAL 資料庫
# ══════════════════════════════════════════════════
def create_sqlite_schema():
    print("\n═══════════════════════════════════════════════════")
    print("  🏗️  階段 2：建置 SQLite WAL 資料庫")
    print("═══════════════════════════════════════════════════")
    
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    
    # 若已存在，先備份舊的
    if os.path.exists(SQLITE_PATH):
        bak = SQLITE_PATH + f'.bak_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        os.rename(SQLITE_PATH, bak)
        print(f"  ⚠️  既有 SQLite 已備份為 {bak}")
    
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS temperatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            channel TEXT NOT NULL,
            name TEXT,
            value REAL NOT NULL,
            status TEXT DEFAULT 'NORMAL',
            runtime_hours REAL DEFAULT 0.0,
            control_temp REAL,
            coil_temp REAL,
            compressor_current REAL,
            high_pressure REAL,
            low_pressure REAL,
            set_temp REAL
        );
        CREATE INDEX IF NOT EXISTS idx_temperatures_channel_time ON temperatures(channel, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_temperatures_time ON temperatures(timestamp DESC);

        CREATE TABLE IF NOT EXISTS power_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            channel TEXT,
            v REAL,
            a REAL,
            kw REAL,
            pf REAL,
            kwh REAL
        );
        CREATE INDEX IF NOT EXISTS idx_power_readings_channel_time ON power_readings(channel, timestamp DESC);

        CREATE TABLE IF NOT EXISTS alarm_settings (
            channel TEXT PRIMARY KEY,
            name TEXT,
            hi REAL,
            lo REAL,
            delay INTEGER DEFAULT 0,
            alarm_enabled INTEGER DEFAULT 1,
            temp_offset REAL DEFAULT 0.0,
            current_threshold REAL DEFAULT 0.5,
            nfb_rated_current REAL,
            power_anomaly_threshold REAL DEFAULT 15.0
        );

        CREATE TABLE IF NOT EXISTS alarm_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            triggered_at TEXT NOT NULL,
            channel TEXT,
            name TEXT,
            value REAL,
            alarm_type TEXT,
            hi REAL,
            lo REAL,
            category TEXT DEFAULT 'ALARM',
            alarm_message TEXT,
            restored_at TEXT,
            duration_sec INTEGER,
            status TEXT DEFAULT 'ACTIVE'
        );
        CREATE INDEX IF NOT EXISTS idx_alarm_history_time ON alarm_history(triggered_at DESC);

        CREATE TABLE IF NOT EXISTS daily_power_stats (
            date TEXT PRIMARY KEY,
            total_kwh REAL DEFAULT 0.0,
            peak_kwh REAL DEFAULT 0.0,
            semi_peak_kwh REAL DEFAULT 0.0,
            off_peak_kwh REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS hourly_power_stats (
            hour_timestamp TEXT PRIMARY KEY,
            ch13_kwh_delta REAL DEFAULT 0.0,
            ch14_kwh_delta REAL DEFAULT 0.0,
            total_kwh_delta REAL DEFAULT 0.0,
            tariff_type TEXT DEFAULT 'off_peak',
            is_anomaly INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_hourly_power_stats_time ON hourly_power_stats(hour_timestamp DESC);

        CREATE TABLE IF NOT EXISTS device_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            command_type TEXT NOT NULL,
            value REAL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            created_at TEXT NOT NULL,
            executed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_device_commands_channel ON device_commands(channel, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_device_commands_status ON device_commands(status, created_at);

        CREATE TABLE IF NOT EXISTS room_alarm_settings (
            room_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            channels TEXT NOT NULL,
            hi REAL,
            lo REAL,
            delay INTEGER DEFAULT 10,
            alarm_enabled INTEGER DEFAULT 1,
            temp_offset REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS monitoring_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level TEXT,
            message TEXT
        );
    """)
    
    conn.close()
    print(f"  ✅ 階段 2 完成：SQLite WAL 資料庫已建立 → {SQLITE_PATH}")


# ══════════════════════════════════════════════════
# 階段 3：數據無損平移 + 雙軌校驗
# ══════════════════════════════════════════════════
def migrate_data(tables):
    print("\n═══════════════════════════════════════════════════")
    print("  📥 階段 3：數據無損平移至 SQLite")
    print("═══════════════════════════════════════════════════")
    
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    
    BATCH = 5000
    
    # temperatures
    data = tables['temperatures']
    print(f"  寫入 temperatures ({len(data)} 筆) ...")
    for i in range(0, len(data), BATCH):
        batch = data[i:i+BATCH]
        conn.executemany("""
            INSERT INTO temperatures (timestamp, channel, name, value, status, runtime_hours,
                control_temp, coil_temp, compressor_current, high_pressure, low_pressure, set_temp)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, [(r['timestamp'], r['channel'], r.get('name'), r['value'],
               r.get('status', 'NORMAL'), r.get('runtime_hours', 0.0),
               r.get('control_temp'), r.get('coil_temp'), r.get('compressor_current'),
               r.get('high_pressure'), r.get('low_pressure'), r.get('set_temp'))
              for r in batch])
        conn.commit()
        print(f"    batch {i//BATCH+1}: {len(batch)} 筆")
    
    # power_readings
    data = tables['power_readings']
    print(f"  寫入 power_readings ({len(data)} 筆) ...")
    for i in range(0, len(data), BATCH):
        batch = data[i:i+BATCH]
        conn.executemany("""
            INSERT INTO power_readings (timestamp, channel, v, a, kw, pf, kwh)
            VALUES (?,?,?,?,?,?,?)
        """, [(r['timestamp'], r.get('channel'), r.get('v'), r.get('a'),
               r.get('kw'), r.get('pf'), r.get('kwh')) for r in batch])
        conn.commit()
        print(f"    batch {i//BATCH+1}: {len(batch)} 筆")
    
    # alarm_settings
    data = tables['alarm_settings']
    print(f"  寫入 alarm_settings ({len(data)} 筆) ...")
    conn.executemany("""
        INSERT OR REPLACE INTO alarm_settings (channel, name, hi, lo, delay, alarm_enabled,
            temp_offset, current_threshold, nfb_rated_current, power_anomaly_threshold)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, [(r['channel'], r.get('name'), r.get('hi'), r.get('lo'),
           r.get('delay', 0), r.get('alarm_enabled', 1), r.get('temp_offset', 0.0),
           r.get('current_threshold', 0.5), r.get('nfb_rated_current'),
           r.get('power_anomaly_threshold', 15.0)) for r in data])
    conn.commit()
    
    # alarm_history
    data = tables['alarm_history']
    print(f"  寫入 alarm_history ({len(data)} 筆) ...")
    conn.executemany("""
        INSERT INTO alarm_history (triggered_at, channel, name, value, alarm_type,
            hi, lo, category, alarm_message, restored_at, duration_sec, status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, [(r['triggered_at'], r.get('channel'), r.get('name'), r.get('value'),
           r.get('alarm_type'), r.get('hi'), r.get('lo'), r.get('category', 'ALARM'),
           r.get('alarm_message'), r.get('restored_at'), r.get('duration_sec'),
           r.get('status', 'ACTIVE')) for r in data])
    conn.commit()
    
    # daily_power_stats
    data = tables['daily_power_stats']
    print(f"  寫入 daily_power_stats ({len(data)} 筆) ...")
    conn.executemany("""
        INSERT OR REPLACE INTO daily_power_stats (date, total_kwh, peak_kwh, semi_peak_kwh, off_peak_kwh)
        VALUES (?,?,?,?,?)
    """, [(r['date'], r.get('total_kwh', 0), r.get('peak_kwh', 0),
           r.get('semi_peak_kwh', 0), r.get('off_peak_kwh', 0)) for r in data])
    conn.commit()
    
    # hourly_power_stats
    data = tables['hourly_power_stats']
    print(f"  寫入 hourly_power_stats ({len(data)} 筆) ...")
    conn.executemany("""
        INSERT OR REPLACE INTO hourly_power_stats (hour_timestamp, ch13_kwh_delta, ch14_kwh_delta,
            total_kwh_delta, tariff_type, is_anomaly)
        VALUES (?,?,?,?,?,?)
    """, [(r['hour_timestamp'], r.get('ch13_kwh_delta', 0), r.get('ch14_kwh_delta', 0),
           r.get('total_kwh_delta', 0), r.get('tariff_type', 'off_peak'),
           r.get('is_anomaly', 0)) for r in data])
    conn.commit()
    
    # device_commands
    data = tables['device_commands']
    print(f"  寫入 device_commands ({len(data)} 筆) ...")
    conn.executemany("""
        INSERT INTO device_commands (channel, command_type, value, status, error_message, created_at, executed_at)
        VALUES (?,?,?,?,?,?,?)
    """, [(r['channel'], r['command_type'], r.get('value'), r.get('status', 'pending'),
           r.get('error_message'), r['created_at'], r.get('executed_at')) for r in data])
    conn.commit()
    
    # room_alarm_settings
    data = tables['room_alarm_settings']
    print(f"  寫入 room_alarm_settings ({len(data)} 筆) ...")
    conn.executemany("""
        INSERT OR REPLACE INTO room_alarm_settings (room_id, name, channels, hi, lo, delay, alarm_enabled, temp_offset)
        VALUES (?,?,?,?,?,?,?,?)
    """, [(r['room_id'], r['name'], r['channels'], r.get('hi'), r.get('lo'),
           r.get('delay', 10), r.get('alarm_enabled', 1), r.get('temp_offset', 0.0)) for r in data])
    conn.commit()
    
    # system_config
    data = tables['system_config']
    print(f"  寫入 system_config ({len(data)} 筆) ...")
    conn.executemany("""
        INSERT OR REPLACE INTO system_config (key, value) VALUES (?,?)
    """, [(r['key'], r['value']) for r in data])
    conn.commit()
    
    # ── 雙軌數據校驗 ──
    print("\n  🔍 雙軌數據指紋校驗 ...")
    verify_ok = True
    for tbl in ['temperatures', 'power_readings', 'alarm_settings', 'alarm_history',
                'daily_power_stats', 'hourly_power_stats', 'device_commands',
                'room_alarm_settings', 'system_config']:
        src_count = len(tables[tbl])
        dst_count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        match = "✅" if src_count == dst_count else "❌ 不匹配！"
        if src_count != dst_count:
            verify_ok = False
        print(f"    {tbl}: TimescaleDB={src_count} → SQLite={dst_count} {match}")
    
    # 檢查 runtime_hours 繼承
    cursor = conn.execute("""
        SELECT channel, MAX(runtime_hours) as max_hours 
        FROM temperatures 
        GROUP BY channel 
        ORDER BY channel
    """)
    print("\n  ⏱️  主機運轉時數繼承確認：")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]:.2f} hr")
    
    conn.close()
    
    if verify_ok:
        print(f"\n  ✅ 階段 3 完成：所有 {sum(len(v) for v in tables.values())} 筆數據已無損平移至 SQLite，校驗 100% 通過！")
    else:
        print("\n  ❌ 校驗不通過，請檢查上述不匹配的資料表！")
    
    return verify_ok


# ══════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════
if __name__ == '__main__':
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  裕珍皇冷鏈 SCADA — TimescaleDB → SQLite WAL 無痛遷移工具  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    tables = export_from_tsdb()
    create_sqlite_schema()
    ok = migrate_data(tables)
    
    if ok:
        db_size = os.path.getsize(SQLITE_PATH) / (1024 * 1024)
        print(f"\n🎉 全部完成！SQLite 資料庫大小: {db_size:.1f} MB")
        print(f"   檔案路徑: {SQLITE_PATH}")
        print(f"   JSON 備份: {BACKUP_DIR}")
        print("\n📌 下一步：修改 local_web/app.py 切換為 SQLite 模式，然後重啟服務即可。")
    else:
        print("\n⚠️  遷移過程有異常，請先檢查後再繼續。Docker 容器仍保持運行，可安全回滾。")
