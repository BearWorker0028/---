from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

import io

import json

import os

import time

import threading

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

from datetime import datetime, timedelta, timezone

from openpyxl import Workbook

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

try:

    import psycopg

    from psycopg.rows import dict_row

except ImportError:

    psycopg = None

    dict_row = None

try:

    from supabase import create_client as _create_supabase_client

except ImportError:

    _create_supabase_client = None

app = Flask(__name__)

app.config['TEMPLATES_AUTO_RELOAD'] = True

@app.after_request

def add_cors_headers(response):

    response.headers['Access-Control-Allow-Origin'] = os.getenv('CORS_ORIGIN', '*')

    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'

    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'

    return response

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()

if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL is required (TimescaleDB/Postgres) — set it in .env')

# 設備控制命令佇列走 Supabase（不是本地 TimescaleDB）：
# 唯一真正碰得到現場 Modbus 的是 GCP 上的 gw1_supabase_collector.py，
# 它透過既有的 W610 連線輪詢 Supabase 的 device_commands 表來執行寫入。
SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
_supabase_client = None

def get_supabase():
    global _supabase_client
    if _supabase_client is None:
        if not _create_supabase_client:
            raise RuntimeError('supabase 套件未安裝，請先執行: pip install supabase')
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError('缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY，請檢查 .env')
        _supabase_client = _create_supabase_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client

TZ_TW_APP = timezone(timedelta(hours=8))

REALTIME_LOCK = threading.Lock()

REALTIME_PAYLOAD = {}

# ── 主機運轉時數累積（壓縮機電流超過各 channel 自訂閾值 且 製冷中 才計時）──
RUNTIME_CURRENT_THRESHOLD_DEFAULT = float(os.getenv('RUNTIME_CURRENT_THRESHOLD', '3.0'))

RUNTIME_LOCK = threading.Lock()

RUNTIME_STATE = {}  # {channel: {'hours': float, 'last_ts': datetime}}

RUNTIME_STATE_LOADED = False

def _load_runtime_state():
    """啟動時從 DB 讀回每個 channel 最後一筆 runtime_hours，避免重啟歸零"""
    global RUNTIME_STATE_LOADED
    if RUNTIME_STATE_LOADED:
        return
    try:
        with get_pg() as conn:
            rows = conn.execute('''
                SELECT DISTINCT ON (channel) channel, runtime_hours
                FROM temperatures
                ORDER BY channel, timestamp DESC, id DESC
            ''').fetchall()
        for row in rows:
            RUNTIME_STATE[row['channel']] = {
                'hours': row['runtime_hours'] or 0.0,
                'last_ts': None
            }
    except Exception:
        pass
    RUNTIME_STATE_LOADED = True

def _update_runtime_hours(items):
    """依壓縮機電流是否超過各 channel 自訂閾值，累積每個 channel 的主機運轉時數（單位：小時）"""
    _load_runtime_state()
    now = datetime.now(TZ_TW_APP)
    alarm_map = _alarm_settings_map()
    with RUNTIME_LOCK:
        for item in items:
            channel = item.get('channel')
            if not channel:
                continue
            current = item.get('compressor_current')
            is_cooling = bool(item.get('cooling_status'))
            ch_setting = alarm_map.get(channel) or {}
            threshold = ch_setting.get('current_threshold')
            if threshold is None:
                threshold = RUNTIME_CURRENT_THRESHOLD_DEFAULT
            is_running = is_cooling and current is not None and float(current) > float(threshold)

            state = RUNTIME_STATE.setdefault(channel, {'hours': 0.0, 'last_ts': None})

            if is_running and state['last_ts'] is not None:
                elapsed_hours = (now - state['last_ts']).total_seconds() / 3600.0
                if 0 < elapsed_hours < 1:  # 忽略斷線重連造成的異常大跳動
                    state['hours'] += elapsed_hours

            state['last_ts'] = now
            item['runtime_hours'] = round(state['hours'], 2)

def get_pg():

    if not psycopg:

        raise RuntimeError('psycopg is required when DATABASE_URL is set')

    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def _fmt_ts(value):

    if isinstance(value, datetime):

        return value.astimezone(TZ_TW_APP).strftime('%Y-%m-%d %H:%M:%S')

    return value

def _payload_to_realtime(payload):

    readings = payload.get('readings', payload)

    if isinstance(readings, dict):

        items = [

            {'channel': ch, **info}

            for ch, info in readings.items()

            if isinstance(info, dict)

        ]

    elif isinstance(readings, list):

        items = readings

    else:

        raise ValueError('readings must be an object or array')

    timestamp = payload.get('timestamp') or datetime.now(TZ_TW_APP).strftime('%Y-%m-%d %H:%M:%S')

    alarm_map = _alarm_settings_map()

    result = {}

    for item in items:

        channel = item.get('channel')

        value = item.get('value')

        if not channel or value is None:

            continue

        value = float(value)

        ch_setting = alarm_map.get(channel, {})

        hi = ch_setting.get('hi')

        lo = ch_setting.get('lo')

        alarm_enabled = ch_setting.get('alarm_enabled')
        alarm_enabled = True if alarm_enabled is None else bool(alarm_enabled)

        result[channel] = {

            **item,

            'channel': channel,

            'name': item.get('name') or ch_setting.get('name') or channel,

            'value': value,

            'timestamp': item.get('timestamp') or timestamp,

            'hi': hi,

            'lo': lo,

            'in_alarm': alarm_enabled and ((hi is not None and value > hi) or (lo is not None and value < lo)),

            'status': item.get('status', 'NORMAL')

        }

    return result

def _alarm_settings_map():

    with get_pg() as conn:

        rows = conn.execute('SELECT * FROM alarm_settings ORDER BY channel').fetchall()

        return {r['channel']: dict(r) for r in rows}

def _latest_temperatures_payload():

    with REALTIME_LOCK:

        if REALTIME_PAYLOAD:

            return dict(REALTIME_PAYLOAD)

    with get_pg() as conn:

        rows = conn.execute('''

            SELECT DISTINCT ON (channel)

                channel, name, value, timestamp, status, runtime_hours

            FROM temperatures

            ORDER BY channel, timestamp DESC, id DESC

        ''').fetchall()

    alarm_map = _alarm_settings_map()

    result = {}

    for row in rows:

        ch = row['channel']

        value = row['value']

        ch_setting = alarm_map.get(ch, {})

        hi = ch_setting.get('hi')

        lo = ch_setting.get('lo')

        alarm_enabled = ch_setting.get('alarm_enabled')
        alarm_enabled = True if alarm_enabled is None else bool(alarm_enabled)

        status = row.get('status') or 'NORMAL'

        result[ch] = {

            'channel': ch,

            'name': row['name'],

            'value': value,

            'timestamp': _fmt_ts(row['timestamp']),

            'hi': hi,

            'lo': lo,

            'in_alarm': alarm_enabled and ((hi is not None and value > hi) or (lo is not None and value < lo)),

            'status': status,

            'runtime_hours': row.get('runtime_hours', 0.0)

        }

    return result

def _normalize_dt(val):
    if not val:
        return datetime.now(TZ_TW_APP)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=TZ_TW_APP)
        return val.astimezone(TZ_TW_APP)
    if isinstance(val, str):
        s = val.strip().replace('T', ' ')
        try:
            if '+' in s or s.endswith('Z'):
                dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
                return dt.astimezone(TZ_TW_APP)
            dt = datetime.strptime(s.split('.')[0], '%Y-%m-%d %H:%M:%S')
            return dt.replace(tzinfo=TZ_TW_APP)
        except Exception:
            return datetime.now(TZ_TW_APP)
    return datetime.now(TZ_TW_APP)

def _save_temperature_payload(payload):
    readings = payload.get('readings', payload)
    if isinstance(readings, dict):
        readings = [
            {'channel': ch, **info}
            for ch, info in readings.items()
            if isinstance(info, dict)
        ]
    if not isinstance(readings, list):
        raise ValueError('readings must be an object or array')

    now = datetime.now(TZ_TW_APP)
    ts_dt = _normalize_dt(payload.get('timestamp'))
    timestamp_str = ts_dt.strftime('%Y-%m-%d %H:%M:%S')

    saved = 0
    with get_pg() as conn:
        with conn.cursor() as cursor:
            for item in readings:
                channel = item.get('channel')
                name = item.get('name') or channel
                value = item.get('value')
                if not channel or value is None:
                    continue

                runtime_hours = float(item.get('runtime_hours', 0.0))
                ctrl_temp = float(item.get('control_temperature', value)) if (item.get('control_temperature') is not None or value is not None) else None
                coil_temp = float(item['coil_temperature']) if item.get('coil_temperature') is not None else None
                compressor_current = float(item['compressor_current']) if item.get('compressor_current') is not None else None
                high_pressure = float(item['high_pressure']) if item.get('high_pressure') is not None else None
                low_pressure = float(item['low_pressure']) if item.get('low_pressure') is not None else None
                set_temp = float(item['control_temperature_set']) if item.get('control_temperature_set') is not None else None

                cursor.execute('''
                    INSERT INTO temperatures (
                        timestamp, channel, name, value, status, runtime_hours,
                        control_temp, coil_temp, compressor_current, high_pressure, low_pressure, set_temp
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    ts_dt, channel, name, float(value), item.get('status', 'NORMAL'), runtime_hours,
                    ctrl_temp, coil_temp, compressor_current, high_pressure, low_pressure, set_temp
                ))
                saved += 1

                pw = item.get('power')
                if pw and isinstance(pw, dict):
                    v = pw.get('voltage_ll_avg') or pw.get('voltage_avg') or pw.get('v')
                    a = pw.get('current_avg') or pw.get('a')
                    kw = pw.get('kw') or (pw.get('power_total', 0) / 1000.0 if pw.get('power_total') is not None else None)
                    pf = pw.get('power_factor') or pw.get('pf')
                    kwh = pw.get('kwh') or (pw.get('energy_total', 0) / 1000.0 if pw.get('energy_total') is not None else None)
                    cursor.execute('''
                        INSERT INTO power_readings (timestamp, channel, v, a, kw, pf, kwh)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        ts_dt, channel,
                        float(v) if v is not None else None,
                        float(a) if a is not None else None,
                        float(kw) if kw is not None else None,
                        float(pf) if pf is not None else None,
                        float(kwh) if kwh is not None else None
                    ))

    return saved, timestamp_str

def _query_temp_range(date_from_str: str, date_to_str: str, channel: str = None):
    """
    溫度查詢：依時間範圍（與 channel，可選）查詢 temperatures。
    回傳 list[dict]，依 timestamp 升序排序。
    """
    dt_from = _normalize_dt(date_from_str)
    dt_to = _normalize_dt(date_to_str)
    q = '''
        SELECT id, timestamp, channel, name, value, status,
               COALESCE(control_temp, value) AS control_temp,
               coil_temp, compressor_current, high_pressure, low_pressure,
               set_temp, COALESCE(runtime_hours, 0.0) AS runtime_hours
        FROM temperatures
        WHERE timestamp BETWEEN %s AND %s
    '''
    params = [dt_from, dt_to]
    if channel:
        q += ' AND channel = %s'
        params.append(channel)
    q += ' ORDER BY timestamp'
    with get_pg() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{**dict(r), 'timestamp': _fmt_ts(r['timestamp'])} for r in rows]

# ============================================================
# 12 通道預設設定
# ============================================================
DEFAULT_CHANNELS = [
    ('ch01', '1F 冷凍庫 A', -15.0, None),
    ('ch02', '1F 冷凍庫 B', -15.0, None),
    ('ch03', '1F 冷凍庫 C', -15.0, None),
    ('ch04', '1F 冷凍庫 D', -15.0, None),
    ('ch05', '1F 冷凍庫 E', -15.0, None),
    ('ch06', '1F 緩衝庫 A', 10.0, None),
    ('ch07', '1F 碼頭區 A', 15.0, None),
    ('ch08', '3F 急速庫 A', -15.0, None),
    ('ch09', '3F 急速庫 B', -15.0, None),
    ('ch10', '3F 半成品庫 A', 8.0, None),
    ('ch11', '3F 半成品庫 B', 8.0, None),
    ('ch12', '3F 冷藏庫 A', 8.0, None),
    ('ch13', '1F 集合式電錶', None, None),
    ('ch14', '3F 集合式電錶', None, None),
]

# D/E/F 庫：僅感溫棒，無壓縮機（iot627 資料只含控制溫度，不含運轉電流）
TEMP_ONLY_ROOMS = {'c', 'd', 'e'}

def init_db():
    with get_pg() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS temperatures (
                    id BIGSERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL,
                    channel TEXT NOT NULL,
                    name TEXT,
                    value DOUBLE PRECISION NOT NULL,
                    status TEXT DEFAULT 'NORMAL',
                    runtime_hours DOUBLE PRECISION DEFAULT 0.0,
                    control_temp DOUBLE PRECISION,
                    coil_temp DOUBLE PRECISION,
                    compressor_current DOUBLE PRECISION,
                    high_pressure DOUBLE PRECISION,
                    low_pressure DOUBLE PRECISION,
                    set_temp DOUBLE PRECISION
                )
            ''')
            for col, col_type in [
                ('runtime_hours', 'DOUBLE PRECISION DEFAULT 0.0'),
                ('control_temp', 'DOUBLE PRECISION'),
                ('coil_temp', 'DOUBLE PRECISION'),
                ('compressor_current', 'DOUBLE PRECISION'),
                ('high_pressure', 'DOUBLE PRECISION'),
                ('low_pressure', 'DOUBLE PRECISION'),
                ('set_temp', 'DOUBLE PRECISION'),
            ]:
                try:
                    cursor.execute(f'ALTER TABLE temperatures ADD COLUMN IF NOT EXISTS {col} {col_type}')
                except Exception:
                    pass

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_temperatures_channel_time ON temperatures (channel, timestamp DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_temperatures_time ON temperatures (timestamp DESC)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alarm_settings (
                    channel TEXT PRIMARY KEY,
                    name TEXT,
                    hi DOUBLE PRECISION,
                    lo DOUBLE PRECISION,
                    delay INTEGER DEFAULT 0,

                    alarm_enabled INTEGER DEFAULT 1,

                    temp_offset DOUBLE PRECISION DEFAULT 0.0,

                    current_threshold DOUBLE PRECISION DEFAULT 0.5,

                    nfb_rated_current DOUBLE PRECISION

                )

            ''')

            cursor.execute('''

                ALTER TABLE alarm_settings ADD COLUMN IF NOT EXISTS current_threshold DOUBLE PRECISION DEFAULT 0.5

            ''')

            cursor.execute('''

                ALTER TABLE alarm_settings ADD COLUMN IF NOT EXISTS nfb_rated_current DOUBLE PRECISION

            ''')

            cursor.execute('''

                ALTER TABLE alarm_settings DROP COLUMN IF EXISTS rated_load_pct

            ''')

            cursor.execute('''

                CREATE TABLE IF NOT EXISTS alarm_history (

                    id BIGSERIAL PRIMARY KEY,

                    triggered_at TIMESTAMPTZ NOT NULL,

                    channel TEXT,

                    name TEXT,

                    value DOUBLE PRECISION,

                    alarm_type TEXT,

                    hi DOUBLE PRECISION,

                    lo DOUBLE PRECISION

                )

            ''')

            cursor.execute('''

                CREATE TABLE IF NOT EXISTS monitoring_logs (

                    id          BIGSERIAL PRIMARY KEY,

                    timestamp   TIMESTAMPTZ NOT NULL,

                    site_code   TEXT NOT NULL,

                    device_no   TEXT NOT NULL,

                    data_key    TEXT NOT NULL,

                    data_value  DOUBLE PRECISION

                )

            ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_monitoring_logs_timestamp ON monitoring_logs (timestamp)')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_monitoring_logs_device_no_key ON monitoring_logs (device_no, data_key)')

            cursor.execute('''

                CREATE TABLE IF NOT EXISTS power_readings (

                    id        BIGSERIAL PRIMARY KEY,

                    timestamp TIMESTAMPTZ NOT NULL,

                    channel   TEXT,

                    v         DOUBLE PRECISION,

                    a         DOUBLE PRECISION,

                    kw        DOUBLE PRECISION,

                    pf        DOUBLE PRECISION,

                    kwh       DOUBLE PRECISION

                )

            ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_power_readings_channel_time ON power_readings (channel, timestamp DESC)')

            for ch, name, hi, lo in DEFAULT_CHANNELS:

                cursor.execute('''

                    INSERT INTO alarm_settings (channel, name, hi, lo)

                    VALUES (%s, %s, %s, %s)

                    ON CONFLICT (channel) DO NOTHING

                ''', (ch, name, hi, lo))

            for ch, name, _, _ in DEFAULT_CHANNELS:

                cursor.execute("UPDATE alarm_settings SET name = %s WHERE channel = %s", (name, ch))

def _get_all_running_hours():
    hours = {}
    try:
        with get_pg() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT site_code, device_no, COUNT(*)
                    FROM monitoring_logs AS m
                    WHERE data_key = 'current' AND (data_value >= 4.0 OR (data_value >= (
                        SELECT MIN(data_value)
                        FROM monitoring_logs
                        WHERE site_code = m.site_code AND device_no = m.device_no AND data_key = 'current'
                    ) + 1.0 AND data_value >= 1.5))
                    GROUP BY site_code, device_no
                ''')
                for r in cursor.fetchall():
                    hours[(r[0], r[1])] = round(r[2] / 60.0, 1)
    except Exception as e:
        print("Failed to query running hours from PG:", e)
    return hours

def _save_realtime_payload_to_logs(timestamp, payload):
    rows = []
    total_kwh = 0.0
    has_power = False
    
    ROOM_NAMES = {
        'a': 'A庫', 'b': 'B庫', 'c': 'D庫', 'd': 'E庫', 'e': 'F庫',
        'g': 'G庫', 'h': 'H庫', 'i1': 'I1庫', 'i2': 'I2庫', 'j': 'J庫', 'k': 'K庫'
    }
    
    for ch, d in payload.items():
        name = ROOM_NAMES.get(ch, ch.upper())
        val = d.get('value')
        if val is not None:
            rows.append((timestamp, name, 'SYSTEM', 'avg_temp', val))
            
        # Power
        pw = d.get('power')
        if pw:
            kw = pw.get('kw')
            kwh = pw.get('kwh')
            if kw is not None and kwh is not None:
                ROOM_PREFIXES = {
                    'a': 'A', 'b': 'B', 'c': 'D', 'd': 'E', 'e': 'F',
                    'g': 'G', 'h': 'H', 'i1': 'I1', 'i2': 'I2', 'j': 'J', 'k': 'K'
                }
                prefix = ROOM_PREFIXES.get(ch, ch.upper())
                meter_no = f"{prefix}-METER-01"
                rows.append((timestamp, name, meter_no, 'kw', kw))
                rows.append((timestamp, name, meter_no, 'kwh', kwh))
                total_kwh += kwh
                has_power = True
                
        # Units
        units = d.get('units')
        if units:
            for u in units:
                dev_id = u.get('id')
                temp = u.get('control_temperature')
                curr = u.get('compressor_current')
                if dev_id and temp is not None:
                    rows.append((timestamp, name, dev_id, 'temp_control', temp))
                    # D/E/F 庫為感溫棒（無壓縮機），不儲存運轉電流
                    if curr is not None and ch not in TEMP_ONLY_ROOMS:
                        rows.append((timestamp, name, dev_id, 'current', curr))
                    
    if has_power:
        rows.append((timestamp, '全廠', 'SYSTEM', 'total_kwh', round(total_kwh, 2)))
        
    if rows:
        try:
            with get_pg() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany('''
                        INSERT INTO monitoring_logs (timestamp, site_code, device_no, data_key, data_value)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', rows)
        except Exception as e:
            print("Postgres log save failed:", e)

def _record_temp_only_iot627_high_alarms(timestamp, payload):
    """Record D/E/F standalone IoT627 high-temperature alarms."""
    ROOM_NAMES = {
        'c': 'D庫',
        'd': 'E庫',
        'e': 'F庫',
    }
    rows = []
    for ch in TEMP_ONLY_ROOMS:
        d = payload.get(ch)
        if not isinstance(d, dict):
            continue
        hi = d.get('hi')
        if hi is None:
            continue
        room_name = ROOM_NAMES.get(ch, d.get('name') or ch.upper())
        units = d.get('units') or []
        iot_units = [u for u in units if isinstance(u, dict) and u.get('type') == 'iot627']
        if not iot_units:
            iot_units = [{'control_temperature': d.get('value')}]
        for unit in iot_units:
            value = unit.get('control_temperature')
            if value is None:
                continue
            value = float(value)
            if value > float(hi):
                rows.append((timestamp, ch, room_name, value, 'HIGH', hi, d.get('lo')))

    if not rows:
        return

    try:
        with get_pg() as conn:
            with conn.cursor() as cursor:
                for row in rows:
                    exists = cursor.execute('''
                        SELECT 1 FROM alarm_history
                        WHERE triggered_at = %s AND channel = %s AND alarm_type = %s
                        LIMIT 1
                    ''', (row[0], row[1], row[4])).fetchone()
                    if exists:
                        continue
                    cursor.execute('''
                        INSERT INTO alarm_history (triggered_at, channel, name, value, alarm_type, hi, lo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', row)
    except Exception as e:
        print("Postgres alarm history save failed:", e)

def _start_mock_data_simulator():
    import random
    import threading
    import time
    import math
    from datetime import datetime
    
    base_temps = {
        'a': -18.0, 'b': -22.0, 'c': 4.0, 'd': 5.0, 'e': -15.0,
        'g': -20.0, 'h': 12.0, 'i1': 0.0, 'i2': 65.0, 'j': 24.0, 'k': 26.0
    }
    
    def run_simulator():
        last_saved_minute = None
        while True:
            payload = {}
            timestamp = datetime.now(TZ_TW_APP).strftime('%Y-%m-%d %H:%M:%S')
            hours_map = _get_all_running_hours()
            for ch in ['a', 'b', 'c', 'd', 'e', 'g', 'h', 'i1', 'i2', 'j', 'k']:
                base = base_temps[ch]
                val = base + random.uniform(-0.5, 0.5)
                base_temps[ch] = val
                
                ROOM_NAMES = {
                    'a': 'A庫', 'b': 'B庫', 'c': 'D庫', 'd': 'E庫', 'e': 'F庫',
                    'g': 'G庫', 'h': 'H庫', 'i1': 'I1庫', 'i2': 'I2庫', 'j': 'J庫', 'k': 'K庫'
                }
                name = ROOM_NAMES.get(ch, ch.upper())
                
                alarm_map = _alarm_settings_map()
                hi = alarm_map.get(ch, {}).get('hi')
                lo = alarm_map.get(ch, {}).get('lo')
                
                in_alarm = False
                status = 'NORMAL'
                if hi is not None and val > hi:
                    in_alarm = True
                    status = 'TRIGGERED'
                elif lo is not None and val < lo:
                    in_alarm = True
                    status = 'TRIGGERED'
                
                # Setup freezer units (iot627 and/or YB-D616-16DI)
                # D, E, F now have 1x iot627 (D-1, E-1, F-1) + 2x YB-D616-16DI
                units = []
                
                # Add iot627 module
                num_units = 3 if ch == 'i1' else (1 if ch in ('c', 'd', 'e') else 2)
                for idx in range(num_units):
                    ROOM_PREFIXES = {
                        'a': 'A', 'b': 'B', 'c': 'D', 'd': 'E', 'e': 'F',
                        'g': 'G', 'h': 'H', 'i1': 'I', 'i2': 'I', 'j': 'J', 'k': 'K'
                    }
                    prefix = ROOM_PREFIXES.get(ch, ch.upper())
                    dev_id = f"{prefix}-{idx + 1}"
                    if ch == 'i1':
                        dev_id = f"I-{idx + 1}"
                    elif ch == 'i2':
                        dev_id = f"I-{idx + 4}"
                    
                    setpoint_t = -18.0 if ch in ('a', 'b', 'e', 'g') else (4.0 if ch == 'c' else (5.0 if ch == 'd' else 65.0))
                    if ch == 'j': setpoint_t = 24.0
                    if ch == 'k': setpoint_t = 26.0

                    t_val = round(val - idx * 0.3, 1)

                    if ch in TEMP_ONLY_ROOMS:
                        # D/E/F 庫：感溫棒模式，無壓縮機，只記錄控制溫度
                        units.append({
                            'id': dev_id,
                            'type': 'iot627',
                            'control_temperature': t_val,
                            'coil_temperature': None,
                            'compressor_current': None,
                            'high_pressure': None,
                            'low_pressure': None,
                            'control_temperature_set': None,
                            'running_status': False,
                            'cooling_status': False,
                            'defrost_status': False,
                            'fan_status': False,
                            'eq_err': False,
                            'temp_err': in_alarm,
                            'total_running_hours': 0
                        })
                    else:
                        is_on = t_val > setpoint_t if base < 20.0 else t_val < setpoint_t
                        if ch in ('j', 'k'): is_on = t_val > setpoint_t

                        curr_val = round(12.5 + random.uniform(-0.8, 0.8), 2) if is_on else round(0.2 + random.uniform(-0.05, 0.05), 2)

                        db_hours = hours_map.get((name, dev_id), 0.0)

                        units.append({
                            'id': dev_id,
                            'type': 'iot627',
                            'control_temperature': t_val,
                            'coil_temperature': round(t_val - 12.0 - idx * 0.8 + random.uniform(-0.5, 0.5), 1),
                            'compressor_current': curr_val,
                            'high_pressure': round(1.45 - idx * 0.07 + random.uniform(-0.1, 0.1), 1),
                            'low_pressure': round(0.12 + idx * 0.03 + random.uniform(-0.02, 0.02), 1),
                            'control_temperature_set': setpoint_t,
                            'running_status': is_on,
                            'cooling_status': is_on,
                            'defrost_status': False,
                            'fan_status': True,
                            'eq_err': False,
                            'temp_err': in_alarm,
                            'total_running_hours': db_hours
                        })

                # Add YB-D616-16DI module if room has it
                has_di = ch in ('c', 'd', 'e', 'j', 'k')
                if has_di:
                    ROOM_PREFIXES = {
                        'a': 'A', 'b': 'B', 'c': 'D', 'd': 'E', 'e': 'F',
                        'g': 'G', 'h': 'H', 'i1': 'I', 'i2': 'I', 'j': 'J', 'k': 'K'
                    }
                    prefix = ROOM_PREFIXES.get(ch, ch.upper())
                    units.append({
                        'id': f"{prefix}-DI-01",
                        'type': 'YB-D616-16DI',
                        'connected': True,
                        'fan_01_running': True, 'fan_01_fault': False,
                        'fan_02_running': True, 'fan_02_fault': False,
                        'fan_03_running': False, 'fan_03_fault': False,
                        'fan_04_running': True, 'fan_04_fault': False,
                        'fan_05_running': True, 'fan_05_fault': False,
                        'fan_06_running': False, 'fan_06_fault': True,
                        'fan_07_running': True, 'fan_07_fault': False,
                        'fan_08_running': True, 'fan_08_fault': False,
                    })
                    units.append({
                        'id': f"{prefix}-DI-02",
                        'type': 'YB-D616-16DI',
                        'connected': True,
                        'fan_09_running': True, 'fan_09_fault': False,
                        'fan_10_running': True, 'fan_10_fault': False,
                        'fan_11_running': False, 'fan_11_fault': False,
                        'fan_12_running': True, 'fan_12_fault': False,
                    })

                idx_ch = ['a', 'b', 'c', 'd', 'e', 'g', 'h', 'i1', 'i2', 'j', 'k'].index(ch)
                rawV = 380.0 + random.uniform(-2.0, 2.0)
                rawA = 24.0 + random.uniform(-1.5, 1.5)
                rawKw = 13.5 + random.uniform(-0.8, 0.8)
                rawKwh = 1543.2 + (time.time() % 100) * 0.1
                rawPf = 0.88 + random.uniform(-0.02, 0.02)
                
                power = {
                    'v': round(rawV, 1),
                    'a': round(rawA, 1),
                    'kw': round(rawKw, 1),
                    'pf': round(rawPf, 1),
                    'kwh': round(rawKwh, 1),
                    'voltage_rs': round(rawV * (1 + math.sin(idx_ch) * 0.003), 1),
                    'voltage_st': round(rawV * (1 + math.cos(idx_ch) * 0.003), 1),
                    'voltage_rt': round(rawV * (1 - math.sin(idx_ch) * 0.003), 1),
                    'voltage_ll_avg': round(rawV, 1),
                    'current_r': round(rawA * (1 + math.sin(idx_ch) * 0.015), 1),
                    'current_s': round(rawA * (1 + math.cos(idx_ch) * 0.015), 1),
                    'current_t': round(rawA * (1 - math.sin(idx_ch) * 0.015), 1),
                    'current_avg': round(rawA, 1),
                    'power_total': round(rawKw * 1000.0, 1),
                    'energy_total': round(rawKwh * 1000.0, 1),
                    'power_factor': round(rawPf, 1)
                }
                
                payload[ch] = {
                    'channel': ch,
                    'name': alarm_map.get(ch, {}).get('name') or ch.upper(),
                    'value': round(val, 1),
                    'timestamp': timestamp,
                    'hi': hi,
                    'lo': lo,
                    'in_alarm': in_alarm,
                    'status': status,
                    'power': power,
                    'flags': {
                        'cooling': True,
                        'defrost': False,
                        'fan': True,
                        'eq_err': False,
                        'temp_err': in_alarm
                    },
                    'units': units
                }
            
            with REALTIME_LOCK:
                REALTIME_PAYLOAD.clear()
                REALTIME_PAYLOAD.update(payload)
            
            curr_min = timestamp[:16]
            if curr_min != last_saved_minute:
                _save_realtime_payload_to_logs(timestamp, payload)
                _record_temp_only_iot627_high_alarms(timestamp, payload)
                last_saved_minute = curr_min
                
            time.sleep(2.0)

    t = threading.Thread(target=run_simulator, daemon=True)
    t.start()

@app.route('/')

def index():

    return render_template('index.html')

@app.route('/remote')

def remote():

    client_ip = request.remote_addr

    forwarded = request.headers.get('X-Forwarded-For', '')

    if forwarded:

        client_ip = forwarded.split(',')[0].strip()

    

    allowed_ips = ['127.0.0.1', '61.222.3.117', '192.168.22.11']

    if client_ip not in allowed_ips and not client_ip.startswith('192.168.'):

        from flask import abort

        abort(403, description=f"拒絕存取：尚未授權此 IP ({client_ip}) 檢視遠端監控畫面。")

        

    return render_template('remote.html')

@app.route('/api/temperatures')

def temperatures():

    return jsonify(_latest_temperatures_payload())

@app.route('/api/temperatures', methods=['POST'])

def add_temperatures():

    try:

        payload = request.get_json(force=True) or {}

        raw_readings = payload.get('readings', payload)

        if isinstance(raw_readings, dict):
            items_for_runtime = [{'channel': ch, **info} for ch, info in raw_readings.items() if isinstance(info, dict)]
        elif isinstance(raw_readings, list):
            items_for_runtime = raw_readings
        else:
            items_for_runtime = []

        _update_runtime_hours(items_for_runtime)

        if isinstance(raw_readings, dict):
            for item in items_for_runtime:
                raw_readings[item['channel']]['runtime_hours'] = item.get('runtime_hours', 0.0)
        payload['readings'] = raw_readings

        realtime_payload = _payload_to_realtime(payload)

        with REALTIME_LOCK:

            REALTIME_PAYLOAD.clear()

            REALTIME_PAYLOAD.update(realtime_payload)

        if payload.get('realtime_only'):
            timestamp = payload.get('timestamp') or datetime.now(TZ_TW_APP).strftime('%Y-%m-%d %H:%M:%S')
            _record_temp_only_iot627_high_alarms(timestamp, realtime_payload)

            return jsonify({

                'status': 'ok',

                'saved': 0,

                'realtime': len(realtime_payload),

                'timestamp': payload.get('timestamp')

            })

        saved, timestamp = _save_temperature_payload(payload)
        _record_temp_only_iot627_high_alarms(timestamp, realtime_payload)

    except (TypeError, ValueError) as exc:

        return jsonify({'error': str(exc)}), 400

    return jsonify({'status': 'ok', 'saved': saved, 'timestamp': timestamp})

@app.route('/api/temperature_stream')

def temperature_stream():

    @stream_with_context

    def event_stream():

        last_payload = None

        while True:

            payload = _latest_temperatures_payload()

            encoded = json.dumps(payload, ensure_ascii=False)

            if encoded != last_payload:

                yield f"event: temperatures\ndata: {encoded}\n\n"

                last_payload = encoded

            else:

                yield ": keepalive\n\n"

            time.sleep(1)

    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/api/alarm_settings', methods=['GET'])

def get_alarm_settings():

    result = {}

    for row in _alarm_settings_map().values():

        result[row['channel']] = {

            'channel': row['channel'],

            'name': row['name'],

            'hi': row['hi'],

            'lo': row['lo'],

            'delay': row.get('delay') or 0,

            'alarm_enabled': row.get('alarm_enabled') if row.get('alarm_enabled') is not None else 1,

            'temp_offset': row.get('temp_offset') or 0.0,

            'current_threshold': row.get('current_threshold') if row.get('current_threshold') is not None else 0.5,

            'nfb_rated_current': row.get('nfb_rated_current')

        }

    return jsonify(result)

@app.route('/api/alarm_settings', methods=['POST'])

def save_alarm_settings():

    data = request.json

    with get_pg() as conn:

        with conn.cursor() as cursor:

            for channel, setting in data.items():

                cursor.execute('''

                    UPDATE alarm_settings

                    SET hi=%s, lo=%s, delay=%s, alarm_enabled=%s, temp_offset=%s, current_threshold=%s, nfb_rated_current=%s

                    WHERE channel=%s

                ''', (setting.get('hi'), setting.get('lo'), setting.get('delay', 0),

                      int(setting.get('alarm_enabled', 1)),

                      float(setting.get('temp_offset', 0)),

                      float(setting.get('current_threshold', 0.5)),

                      (float(setting['nfb_rated_current']) if setting.get('nfb_rated_current') not in (None, '') else None),
                      channel))

    return jsonify({'status': 'ok'})

# ============================================================

# 警報歷史

# ============================================================

@app.route('/api/alarm_history')

def alarm_history():

    channel   = request.args.get('channel', 'all')

    date_from = request.args.get('from', None)

    date_to   = request.args.get('to',   None)

    limit     = int(request.args.get('limit', 200))

    conditions, params = [], []

    if channel != 'all':

        conditions.append('channel = %s')

        params.append(channel)

    if date_from:

        conditions.append('triggered_at >= %s')

        params.append(date_from)

    if date_to:

        to_str = date_to if len(date_to) > 10 else date_to + ' 23:59:59'

        conditions.append('triggered_at <= %s')

        params.append(to_str)

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    with get_pg() as conn:

        records = conn.execute(f'''

            SELECT id, triggered_at, channel, name, value, alarm_type, hi, lo

            FROM alarm_history {where}

            ORDER BY triggered_at DESC LIMIT %s

        ''', params + [limit]).fetchall()

        summary_rows = conn.execute(f'''

            SELECT channel, name,

                   COUNT(*) as total,

                   SUM(CASE WHEN alarm_type='HIGH' THEN 1 ELSE 0 END) as high_cnt,

                   SUM(CASE WHEN alarm_type='LOW'  THEN 1 ELSE 0 END) as low_cnt

            FROM alarm_history {where} GROUP BY channel, name ORDER BY total DESC

        ''', params).fetchall()

    return jsonify({

        'records': [{**dict(r), 'triggered_at': _fmt_ts(r['triggered_at'])} for r in records],

        'summary': [dict(r) for r in summary_rows],

        'total': len(records)

    })

@app.route('/api/alarm_history', methods=['POST'])

def add_alarm_history():

    data = request.json

    tw_now = datetime.now(TZ_TW_APP).strftime('%Y-%m-%d %H:%M:%S')

    with get_pg() as conn:

        conn.execute('''

            INSERT INTO alarm_history (triggered_at, channel, name, value, alarm_type, hi, lo)

            VALUES (%s, %s, %s, %s, %s, %s, %s)

        ''', (tw_now, data['channel'], data['name'], data['value'],

              data['alarm_type'], data['hi'], data['lo']))

    return jsonify({'status': 'ok'})

# ============================================================

# 設備控制命令佇列
# 前端寫入 pending 命令 → Supabase device_commands 表
# → GCP 上的 gw1_supabase_collector.py 用既有的 W610 連線輪詢執行、回報結果
# set_temperature：對應 IoT627 40007 控制溫度設定
# set_power_state：對應 IoT627 40179 (A801 停控模式)，1=全開 0=全停（實測確認位址）
# ============================================================

SUPPORTED_COMMAND_TYPES = {'set_temperature', 'set_power_state'}

@app.route('/api/device_commands', methods=['POST'])
def create_device_command():
    data = request.json or {}
    channel = data.get('channel')
    command_type = data.get('command_type')
    value = data.get('value')

    if not channel:
        return jsonify({'error': 'channel is required'}), 400
    if command_type not in SUPPORTED_COMMAND_TYPES:
        return jsonify({'error': f'unsupported command_type: {command_type}'}), 400
    if command_type == 'set_temperature':
        try:
            value = float(value)
        except (TypeError, ValueError):
            return jsonify({'error': 'value must be a number for set_temperature'}), 400
        if not (-60 <= value <= 60):
            return jsonify({'error': 'value out of safe range (-60~60 degC)'}), 400
    elif command_type == 'set_power_state':
        try:
            value = float(value)
        except (TypeError, ValueError):
            return jsonify({'error': 'value must be 0 or 1 for set_power_state'}), 400
        if value not in (0, 1):
            return jsonify({'error': 'value must be 0 (停) or 1 (開) for set_power_state'}), 400

    resp = get_supabase().table('device_commands').insert({
        'channel': channel,
        'command_type': command_type,
        'value': value,
        'status': 'pending'
    }).execute()

    return jsonify({'status': 'ok', 'id': resp.data[0]['id']})

@app.route('/api/device_commands', methods=['GET'])
def list_device_commands():
    status = request.args.get('status')
    channel = request.args.get('channel')
    limit = int(request.args.get('limit', 50))

    q = get_supabase().table('device_commands').select('*')
    if status:
        q = q.eq('status', status)
    if channel:
        q = q.eq('channel', channel)
    resp = q.order('created_at', desc=True).limit(limit).execute()

    return jsonify(resp.data)

@app.route('/api/device_commands/<int:command_id>', methods=['GET'])
def get_device_command(command_id):
    resp = get_supabase().table('device_commands').select('*').eq('id', command_id).execute()
    if not resp.data:
        return jsonify({'error': 'not found'}), 404
    return jsonify(resp.data[0])

@app.route('/api/device_commands/<int:command_id>/complete', methods=['POST'])
def complete_device_command(command_id):
    data = request.json or {}
    success = bool(data.get('success'))
    error_message = data.get('error_message')

    get_supabase().table('device_commands').update({
        'status': 'success' if success else 'failed',
        'error_message': error_message,
        'executed_at': datetime.now(TZ_TW_APP).strftime('%Y-%m-%d %H:%M:%S')
    }).eq('id', command_id).execute()

    return jsonify({'status': 'ok'})

# ============================================================

# 圖表資料

# ============================================================

@app.route('/api/chart_data')
def chart_data():
    range_type = request.args.get('range', 'realtime')
    date_from  = request.args.get('from', None)
    date_to    = request.args.get('to',   None)
    now_tw = datetime.now(TZ_TW_APP)

    if range_type == 'custom' and date_from and date_to:
        from_str = date_from
        to_str   = date_to
    else:
        minutes_map = {'realtime': 60, '1h': 60, '4h': 240, '6h': 360, '24h': 1440}
        minutes = minutes_map.get(range_type, 60)
        from_str = (now_tw - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
        to_str   = now_tw.strftime('%Y-%m-%d %H:%M:%S')

    rows = _query_temp_range(from_str, to_str)
    alarm_map = _alarm_settings_map()

    series = {}
    for row in rows:
        ch = row['channel']
        if ch not in series:
            series[ch] = {'name': row['name'] or ch, 'data': []}
        series[ch]['data'].append({
            't': row['timestamp'],
            'v': row['value'],
            'control_temp': row.get('control_temp', row['value']),
            'coil_temp': row.get('coil_temp'),
            'compressor_current': row.get('compressor_current'),
            'high_pressure': row.get('high_pressure'),
            'low_pressure': row.get('low_pressure'),
            'set_temp': row.get('set_temp'),
            'runtime_hours': row.get('runtime_hours', 0.0)
        })

    stats = {}
    for ch, s in series.items():
        vals  = [d['v'] for d in s['data'] if d.get('v') is not None]
        times = [d['t'] for d in s['data']]
        if vals:
            max_v = max(vals)
            min_v = min(vals)
            hi    = alarm_map.get(ch, {}).get('hi')
            lo    = alarm_map.get(ch, {}).get('lo')
            ch_alarm_enabled = alarm_map.get(ch, {}).get('alarm_enabled')
            ch_alarm_enabled = True if ch_alarm_enabled is None else bool(ch_alarm_enabled)
            stats[ch] = {
                'name':     s['name'],
                'max':      round(max_v, 1),
                'max_time': times[vals.index(max_v)],
                'min':      round(min_v, 1),
                'min_time': times[vals.index(min_v)],
                'avg':      round(sum(vals)/len(vals), 1),
                'count':    len(vals),
                'in_alarm': ch_alarm_enabled and any(
                    (hi is not None and v > hi) or (lo is not None and v < lo)
                    for v in vals
                ),
                'hi': hi,
                'lo': lo
            }

    return jsonify({'series': series, 'stats': stats, 'alarm_map': alarm_map})

@app.route('/api/power_chart_data')
def power_chart_data():
    channels   = request.args.getlist('ch')   # e.g. ?ch=ch13&ch=ch14
    field      = request.args.get('field', 'energy_total')   # power_total / energy_total / etc
    range_type = request.args.get('range', 'realtime')
    date_from  = request.args.get('from', None)
    date_to    = request.args.get('to',   None)

    field_mapping = {
        'power_total': ('kw', 1.0),
        'energy_total': ('kwh', 1.0),
        'voltage_ll_avg': ('v', 1.0),
        'voltage_avg': ('v', 1.0),
        'current_avg': ('a', 1.0),
        'power_factor': ('pf', 1.0),
        'v': ('v', 1.0),
        'a': ('a', 1.0),
        'kw': ('kw', 1.0),
        'pf': ('pf', 1.0),
        'kwh': ('kwh', 1.0)
    }
    mapped = field_mapping.get(field)
    if not mapped:
        field = 'energy_total'
        mapped = ('kwh', 1.0)
    db_col, scale = mapped

    now_tw = datetime.now(TZ_TW_APP)
    if range_type == 'custom' and date_from and date_to:
        from_str = date_from
        to_str   = date_to
    else:
        minutes_map = {'realtime': 60, '1h': 60, '4h': 240, '6h': 360, '24h': 1440}
        minutes  = minutes_map.get(range_type, int(request.args.get('minutes', 60)))
        from_str = (now_tw - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
        to_str   = now_tw.strftime('%Y-%m-%d %H:%M:%S')

    series = {}
    with get_pg() as conn:
        for ch in channels:
            rows = conn.execute(
                f'SELECT timestamp, {db_col} as val FROM power_readings '
                f'WHERE channel=%s AND timestamp>=%s AND timestamp<=%s ORDER BY timestamp',
                (ch, from_str, to_str)
            ).fetchall()
            series[ch] = [{'t': _fmt_ts(r['timestamp']), 'v': round(r['val'] * scale, 1) if r['val'] is not None else None} for r in rows]

    return jsonify({'series': series, 'field': field})

@app.route('/api/report/download')
def report_download():
    report_type = request.args.get('type', 'month')
    room        = request.args.get('room', 'a')
    device_type = request.args.get('device_type', 'room_summary')
    device_idx  = request.args.get('device_idx', '1')
    info_key    = request.args.get('info_key', 'all_info')

    # Get Chinese name for the room
    ROOM_NAMES = {
        'a': 'A庫', 'b': 'B庫', 'c': 'D庫', 'd': 'E庫', 'e': 'F庫',
        'g': 'G庫', 'h': 'H庫', 'i1': 'I1庫', 'i2': 'I2庫', 'j': 'J庫', 'k': 'K庫',
        'all': '全廠'
    }
    site_code = ROOM_NAMES.get(room, room)

    ROOM_PREFIXES = {
        'a': 'A', 'b': 'B', 'c': 'D', 'd': 'E', 'e': 'F',
        'g': 'G', 'h': 'H', 'i1': 'I1', 'i2': 'I2', 'j': 'J', 'k': 'K'
    }
    prefix = ROOM_PREFIXES.get(room, room.upper())

    # Map SQL query conditions based on info_key and device_type
    query_cond = ""
    query_params = ()
    device_no = ""
    data_key = ""

    if info_key == 'all_info':
        if device_type == 'room_summary':
            query_cond = f"(device_no = 'SYSTEM' AND data_key = 'avg_temp') OR (device_no = '{prefix}-METER-01' AND data_key IN ('kw', 'kwh'))"
            query_params = ()
            device_no = "全庫整體"
        elif device_type == 'iot627':
            if room == 'i1':
                device_no = f"I-{device_idx}"
            elif room == 'i2':
                device_no = f"I-{int(device_idx) + 3}"
            else:
                device_no = f"{prefix}-{device_idx}"
            if room in TEMP_ONLY_ROOMS:
                # D/E/F 庫：感溫棒，無壓縮機電流
                query_cond = "device_no = %s AND data_key = 'temp_control'"
            else:
                query_cond = "device_no = %s AND data_key IN ('temp_control', 'current')"
            query_params = (device_no,)
        elif device_type == 'S2-800MT':
            device_no = f"{prefix}-METER-01"
            query_cond = "device_no = %s AND data_key IN ('kw', 'kwh')"
            query_params = (device_no,)
        elif device_type == 'factory':
            device_no = 'SYSTEM'
            query_cond = "device_no = 'SYSTEM' AND data_key = 'total_kwh'"
            query_params = ()
    else:
        # Single parameter mapping
        if device_type == 'room_summary':
            if info_key == 'avg_temp':
                device_no = 'SYSTEM'
                data_key = 'avg_temp'
            else:
                device_no = f"{prefix}-METER-01"
                data_key = info_key
        elif device_type == 'iot627':
            if room == 'i1':
                device_no = f"I-{device_idx}"
            elif room == 'i2':
                device_no = f"I-{int(device_idx) + 3}"
            else:
                device_no = f"{prefix}-{device_idx}"
                
            if info_key == 'running_hours':
                data_key = 'current'
            elif info_key == 'control_temperature':
                data_key = 'temp_control'
            else:
                data_key = info_key
        elif device_type == 'S2-800MT':
            device_no = f"{prefix}-METER-01"
            data_key = info_key
        elif device_type == 'factory':
            device_no = 'SYSTEM'
            data_key = info_key
        else:
            return jsonify({'error': '無效的設備類型'}), 400
            
        query_cond = "device_no = %s AND data_key = %s"
        query_params = (device_no, data_key)

    # Calculate time range
    date_param = request.args.get('date', '')
    if not date_param:
        date_param = datetime.now().strftime('%Y-%m-%d')
        
    try:
        selected_date = datetime.strptime(date_param, '%Y-%m-%d')
    except Exception as e:
        return jsonify({'error': f'無效的日期格式: {date_param}'}), 400

    if report_type == 'day':
        d_from = selected_date.replace(hour=0, minute=0, second=0, microsecond=0)
        d_to = selected_date.replace(hour=23, minute=59, second=59, microsecond=0)
        file_label = date_param
        report_name = '日報表'
    elif report_type == 'week':
        monday = selected_date - timedelta(days=selected_date.weekday())
        d_from = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        sunday = monday + timedelta(days=6)
        d_to = sunday.replace(hour=23, minute=59, second=59, microsecond=0)
        file_label = f"W{monday.strftime('%Y-%m-%d')}_至_{sunday.strftime('%Y-%m-%d')}"
        report_name = '周報表'
    elif report_type == 'month':
        d_from = selected_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if d_from.month == 12:
            d_to = datetime(d_from.year, 12, 31, 23, 59, 59)
        else:
            d_to = (datetime(d_from.year, d_from.month + 1, 1) - timedelta(seconds=1))
        file_label = d_from.strftime('%Y-%m')
        report_name = '月報表'
    else:
        return jsonify({'error': '無效的報表類型'}), 400

    date_from = d_from.strftime('%Y-%m-%d %H:%M:%S')
    date_to   = d_to.strftime('%Y-%m-%d %H:%M:%S')

    # Query database
    sql = f'''
        SELECT timestamp, data_key, data_value
        FROM monitoring_logs
        WHERE site_code=%s AND ({query_cond})
          AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp
    '''
    with get_pg() as conn:
        rows = [{**dict(r), 'timestamp': _fmt_ts(r['timestamp'])} for r in conn.execute(sql, (site_code,) + query_params + (date_from, date_to)).fetchall()]

    # Determine sampling interval in minutes
    sampling_param = request.args.get('sampling', 'false')
    sampling_enabled = (sampling_param.lower() in ('true', '1', 'yes'))
    interval_minutes = 1
    if sampling_enabled:
        if report_type == 'week':
            interval_minutes = 5
        elif report_type == 'month':
            interval_minutes = 30

    # Calculate exact total running minutes and total monitoring minutes from 1-minute raw database logs (for iot627 running hours)
    current_vals = [r['data_value'] for r in rows if r['data_key'] == 'current' and r['data_value'] is not None]
    min_current = min(current_vals) if current_vals else None
    
    raw_running_minutes = 0
    raw_total_minutes = 0
    for r in rows:
        if r['data_key'] == 'current' and r['data_value'] is not None:
            raw_total_minutes += 1
            val = r['data_value']
            is_running = False
            if val >= 4.0:
                is_running = True
            elif min_current is not None and val >= min_current + 1.0 and val >= 1.5:
                is_running = True
            elif min_current is None and val >= 1.5:
                is_running = True
            if is_running:
                raw_running_minutes += 1

    # Process data buckets (average per sampling interval for each key)
    from collections import defaultdict
    bucket_keys = defaultdict(lambda: defaultdict(list))
    for r in rows:
        try:
            r_dt = datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S')
            floored_minute = (r_dt.minute // interval_minutes) * interval_minutes
            bucket_time = r_dt.replace(minute=floored_minute, second=0, microsecond=0)
            bucket_key = bucket_time.strftime('%Y-%m-%d %H:%M')
            if r['data_value'] is not None:
                bucket_keys[bucket_key][r['data_key']].append(r['data_value'])
        except Exception as e:
            pass
            
    data_map = {}
    for t, keys_map in bucket_keys.items():
        data_map[t] = {k: sum(v)/len(v) for k, v in keys_map.items()}

    current_time = d_from
    end_time_minute = d_to.replace(second=0, microsecond=0)
    
    report_data = []
    summary_vals = defaultdict(list)

    while current_time <= end_time_minute:
        t_str = current_time.strftime('%Y-%m-%d %H:%M')
        val_dict = data_map.get(t_str, {})
        status_str = '正常' if val_dict else '無效'
        
        if info_key == 'all_info':
            if device_type == 'room_summary':
                t_val = val_dict.get('avg_temp')
                kw_val = val_dict.get('kw')
                kwh_val = val_dict.get('kwh')
                
                t_str_val = f"{round(t_val, 1)}" if t_val is not None else '-'
                kw_str_val = f"{round(kw_val, 1)}" if kw_val is not None else '-'
                kwh_str_val = f"{round(kwh_val, 1)}" if kwh_val is not None else '-'
                
                if t_val is not None: summary_vals['avg_temp'].append(t_val)
                if kw_val is not None: summary_vals['kw'].append(kw_val)
                if kwh_val is not None: summary_vals['kwh'].append(kwh_val)
                
                report_data.append((t_str, t_str_val, kw_str_val, kwh_str_val, status_str))
                
            elif device_type == 'iot627':
                t_val = val_dict.get('temp_control')
                t_str_val = f"{round(t_val, 1)}" if t_val is not None else '-'
                if room in TEMP_ONLY_ROOMS:
                    # D/E/F 庫：感溫棒，無壓縮機，只顯示控制溫度
                    if t_val is not None: summary_vals['temp_control'].append(t_val)
                    report_data.append((t_str, t_str_val, status_str))
                else:
                    c_val = val_dict.get('current')
                    if c_val is not None:
                        is_running = False
                        if c_val >= 4.0:
                            is_running = True
                        elif min_current is not None and c_val >= min_current + 1.0 and c_val >= 1.5:
                            is_running = True
                        elif min_current is None and c_val >= 1.5:
                            is_running = True
                        run_str = '運轉' if is_running else '停機'
                        summary_vals['current'].append(c_val)
                    else:
                        run_str = '-'
                    if t_val is not None: summary_vals['temp_control'].append(t_val)
                    report_data.append((t_str, t_str_val, run_str, status_str))
                
            elif device_type == 'S2-800MT':
                kw_val = val_dict.get('kw')
                kwh_val = val_dict.get('kwh')
                
                kw_str_val = f"{round(kw_val, 1)}" if kw_val is not None else '-'
                kwh_str_val = f"{round(kwh_val, 1)}" if kwh_val is not None else '-'
                
                if kw_val is not None: summary_vals['kw'].append(kw_val)
                if kwh_val is not None: summary_vals['kwh'].append(kwh_val)
                
                report_data.append((t_str, kw_str_val, kwh_str_val, status_str))
                
            elif device_type == 'factory':
                kwh_val = val_dict.get('total_kwh')
                kwh_str_val = f"{round(kwh_val, 1)}" if kwh_val is not None else '-'
                if kwh_val is not None: summary_vals['total_kwh'].append(kwh_val)
                report_data.append((t_str, kwh_str_val, status_str))
        else:
            # Single parameter
            v = val_dict.get(data_key)
            if info_key == 'running_hours':
                if v is not None:
                    is_running = False
                    if v >= 4.0:
                        is_running = True
                    elif min_current is not None and v >= min_current + 1.0 and v >= 1.5:
                        is_running = True
                    elif min_current is None and v >= 1.5:
                        is_running = True
                    status_str = '運轉' if is_running else '停機'
                    report_data.append((t_str, round(v, 1), status_str))
                    summary_vals['running_hours'].append(v)
                else:
                    report_data.append((t_str, '-', '無效'))
            else:
                if v is not None:
                    v_rounded = round(v, 1)
                    summary_vals[info_key].append(v_rounded)
                    report_data.append((t_str, v_rounded, '正常'))
                else:
                    report_data.append((t_str, '-', '無效'))
                    
        current_time += timedelta(minutes=interval_minutes)

    # Create Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = '資訊摘要'

    accent_fill  = PatternFill(fill_type='solid', fgColor='1A5FA8')
    alarm_fill   = PatternFill(fill_type='solid', fgColor='FDECEA')
    header_font  = Font(name='Arial', bold=True, color='FFFFFF', size=11)
    label_font   = Font(name='Arial', bold=True, size=10)
    value_font   = Font(name='Arial', size=10)
    alarm_font   = Font(name='Arial', color='C0392B', size=10)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align   = Alignment(horizontal='left',   vertical='center')
    thin         = Side(border_style='thin', color='DDDDDD')
    cell_border  = Border(left=thin, right=thin, top=thin, bottom=thin)

    def set_hdr(ws, row, col, text, merge_to=None):
        c = ws.cell(row=row, column=col, value=text)
        c.font = header_font; c.fill = accent_fill
        c.alignment = center_align; c.border = cell_border
        if merge_to:
            ws.merge_cells(f'{c.coordinate}:{merge_to}')

    def set_lbl(ws, row, col, text):
        c = ws.cell(row=row, column=col, value=text)
        c.font = label_font; c.alignment = left_align; c.border = cell_border

    def set_val(ws, row, col, text):
        c = ws.cell(row=row, column=col, value=text)
        c.font = value_font; c.alignment = left_align; c.border = cell_border

    # Label translation for metadata
    PARAM_LABELS = {
        'avg_temp': ('平均庫溫', '°C'),
        'temp_control': ('控制溫度', '°C'),
        'control_temperature': ('控制溫度', '°C'),
        'current': ('運轉電流', 'A'),
        'running_hours': ('主機運轉狀態', ''),
        'kw': ('即時耗電量', 'kW'),
        'kwh': ('累積用電量', 'kWh'),
        'total_kwh': ('總累積耗電量', 'kWh'),
        'all_info': ('全部資訊', '')
    }
    param_label, unit = PARAM_LABELS.get(info_key, (info_key, ''))

    # Title Banner
    ws.merge_cells('A1:D1')
    ws['A1'].value     = f'{site_code} {param_label} {report_name}'
    ws['A1'].font      = Font(name='Arial', bold=True, size=16, color='1A5FA8')
    ws['A1'].alignment = center_align
    ws.row_dimensions[1].height = 36

    ws.merge_cells('A2:D2')
    ws['A2'].value     = f'生成時間：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    ws['A2'].font      = Font(name='Arial', size=9, color='888888')
    ws['A2'].alignment = left_align

    # Info Header
    ws.merge_cells('A3:D3')
    set_hdr(ws, 3, 1, '報 表 資 訊 摘 要')
    for col in range(2, 5):
        ws.cell(3, col).fill = accent_fill

    if device_type == 'iot627' and room in TEMP_ONLY_ROOMS:
        device_label = '庫溫監控器'
    else:
        device_label = device_type.replace("room_summary", "全庫").replace("iot627", "冷凍主機").replace("S2-800MT", "電表").replace("factory", "廠區")

    # Build Info Rows
    info_rows = [
        ('查詢範圍', f'{site_code} ({room.upper()})'),
        ('設備名稱', f'{device_label} #{device_idx}'),
        ('數據項目', f'{param_label} ({unit})' if unit else param_label),
        ('起始時間', date_from),
        ('結束時間', date_to)
    ]
    
    # helper functions for statistics
    def add_kwh_stats(rows_list, label_title, vals_list):
        rows_list.append((f'【{label_title}】', ''))
        s_val = vals_list[0] if vals_list else '-'
        e_val = vals_list[-1] if vals_list else '-'
        consumed = round(e_val - s_val, 1) if isinstance(s_val, (int, float)) and isinstance(e_val, (int, float)) else '-'
        rows_list.extend([
            ('  起始電量', f'{s_val} kWh'),
            ('  結束電量', f'{e_val} kWh'),
            ('  總用電量', f'{consumed} kWh')
        ])

    def add_num_stats(rows_list, label_title, vals_list, unit_str):
        rows_list.append((f'【{label_title}】', ''))
        mx = round(max(vals_list), 1) if vals_list else '-'
        mn = round(min(vals_list), 1) if vals_list else '-'
        av = round(sum(vals_list)/len(vals_list), 1) if vals_list else '-'
        rows_list.extend([
            ('  最大值', f'{mx} {unit_str}' if mx != '-' else '-'),
            ('  最小值', f'{mn} {unit_str}' if mn != '-' else '-'),
            ('  平均值', f'{av} {unit_str}' if av != '-' else '-')
        ])

    def add_run_stats(rows_list, label_title):
        rows_list.append((f'【{label_title}】', ''))
        dur_h = raw_total_minutes / 60.0
        run_h = raw_running_minutes / 60.0
        ratio = round((run_h / dur_h) * 100.0, 1) if dur_h > 0 else 0.0
        rows_list.extend([
            ('  總監測時數', f'{round(dur_h, 2)} 小時'),
            ('  累積運轉時數', f'{round(run_h, 2)} 小時'),
            ('  運轉率', f'{ratio} %'),
            ('  判定標準', '動靜態自適應判讀')
        ])

    if info_key == 'all_info':
        if device_type == 'room_summary':
            add_num_stats(info_rows, '平均庫溫', summary_vals['avg_temp'], '°C')
            add_num_stats(info_rows, '即時耗電量', summary_vals['kw'], 'kW')
            add_kwh_stats(info_rows, '累積耗電量', summary_vals['kwh'])
        elif device_type == 'iot627':
            add_num_stats(info_rows, '控制溫度', summary_vals['temp_control'], '°C')
            if room not in TEMP_ONLY_ROOMS:
                # 不是 D/E/F 庫才顯示主機運轉時數
                add_run_stats(info_rows, '主機運轉時數')
        elif device_type == 'S2-800MT':
            add_num_stats(info_rows, '即時耗電量', summary_vals['kw'], 'kW')
            add_kwh_stats(info_rows, '累積耗電量', summary_vals['kwh'])
        elif device_type == 'factory':
            add_kwh_stats(info_rows, '總累積耗電量', summary_vals['total_kwh'])
    else:
        # Single parameter summary
        if info_key == 'running_hours':
            add_run_stats(info_rows, '主機運轉狀態')
        elif info_key in ('kwh', 'total_kwh'):
            add_kwh_stats(info_rows, param_label, summary_vals[info_key])
        else:
            add_num_stats(info_rows, param_label, summary_vals[info_key], unit)

    for i, (label, val_text) in enumerate(info_rows, start=4):
        set_lbl(ws, i, 1, label)
        ws.merge_cells(f'B{i}:D{i}')
        set_val(ws, i, 2, val_text)
        for col in range(3, 5):
            ws.cell(i, col).border = cell_border

    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 16
    ws.column_dimensions['D'].width = 16

    # ── 數據工作表 ──
    wd = wb.create_sheet('歷史數據明細')
    
    if info_key == 'all_info':
        if device_type == 'room_summary':
            headers = ['時間', '平均庫溫 (°C)', '即時耗電量 (kW)', '累積耗電量 (kWh)', '狀態']
            col_widths = [20, 18, 16, 18, 12]
        elif device_type == 'iot627':
            if room in TEMP_ONLY_ROOMS:
                # D/E/F 庫：感溫棒模式，只有溫度欄
                headers = ['時間', '控制溫度 (°C)', '狀態']
                col_widths = [20, 18, 12]
            else:
                headers = ['時間', '控制溫度 (°C)', '主機運轉狀態', '狀態']
                col_widths = [20, 18, 16, 12]
        elif device_type == 'S2-800MT':
            headers = ['時間', '即時耗電量 (kW)', '累積耗電量 (kWh)', '狀態']
            col_widths = [20, 16, 18, 12]
        elif device_type == 'factory':
            headers = ['時間', '總累積耗電量 (kWh)', '狀態']
            col_widths = [20, 20, 12]
    else:
        if info_key == 'running_hours':
            headers = ['時間', '運轉電流 (A)', '運行狀態']
            col_widths = [20, 16, 12]
        else:
            headers = ['時間', f'{param_label} ({unit})' if unit else param_label, '狀態']
            col_widths = [20, 16, 12]
        
    for col, (h, w) in enumerate(zip(headers, col_widths), 1):
        set_hdr(wd, 1, col, h)
        wd.column_dimensions[chr(64+col)].width = w

    for r_idx, row_vals in enumerate(report_data, 2):
        for col, cell_val in enumerate(row_vals, 1):
            c = wd.cell(r_idx, col, cell_val)
            c.border = cell_border
            c.alignment = left_align
            if cell_val in ('運轉', '正常', '停機', '無效'):
                c.alignment = center_align
            if cell_val in ('運轉', '⚠ 超標'):
                c.fill = alarm_fill
                c.font = alarm_font
            elif cell_val in ('停機', '無效'):
                c.font = Font(name='Arial', color='888888', size=10)

    # Save to buffer
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f'報表_{site_code}_{param_label}_{file_label}.xlsx'
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
init_db()

MOCK_DATA_ENABLED = os.getenv('MOCK_DATA_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')

if MOCK_DATA_ENABLED:
    _start_mock_data_simulator()

if __name__ == '__main__':

    import sys

    if sys.platform == 'win32':

        from waitress import serve

        serve(app, host='0.0.0.0', port=88)

    else:

        app.run(debug=True, host='0.0.0.0', port=88)

