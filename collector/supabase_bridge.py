# -*- coding: utf-8 -*-
"""
【臨時資料橋接】從 Supabase 即時狀態表抓資料 → 推送到本機 Flask (/api/temperatures)

用途：
  GW1/GW2 現場的 W610 Gateway 已經撥出連到 GCP，GCP 上的
  collector/gw1_supabase_collector.py、gw2_supabase_collector.py
  正在把最新讀值 upsert 進 Supabase 的 gw1_temp_status / gw2_temp_status /
  gw1_meter_status / gw2_meter_status 四張表。

  在還沒確認 GW2 真實 IP、還沒能在裕珍皇現場直接連 Modbus 之前，
  這支腳本先扮演 modbus_reader.py 的角色：定時把 Supabase 最新狀態
  轉換成跟 modbus_reader.py 完全相同的 payload 格式，POST 給本機
  local_web/app.py 的 /api/temperatures，讓地端電視牆可以立刻顯示
  接近即時的真實數據。

  這是過渡方案，資料本身仍然只有「最新狀態」(Supabase 表是 upsert，
  沒有歷史)，2 年時序歷史要等本機 modbus_reader.py 直接讀 Modbus、
  寫進季度 DB 才算數。

如何切換回正式模式：
  1. 確認 GW2 真實 IP，填入 collector/channel_config.json 與
     config/site_config.json
  2. 在裕珍皇現場網段的主機上，Ctrl+C 停掉這支腳本
  3. 改跑：python collector/modbus_reader.py
  兩者都是 POST 同一個 /api/temperatures，app.py 與前端完全不用改。

執行方式：
  1. 先啟動 local_web/app.py（提供 /api/temperatures 端點）
  2. 另開一個終端機，執行本腳本：
     python collector/supabase_bridge.py
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

try:
    from supabase import create_client
except ImportError:
    print("缺少 supabase 套件，請先執行: pip install supabase")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
load_dotenv(os.path.join(ROOT_DIR, '.env'))

TZ_TW = timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
API_BASE = os.getenv('API_BASE', 'http://127.0.0.1:88').rstrip('/')
POLL_INTERVAL = float(os.getenv('SUPABASE_BRIDGE_INTERVAL', '4'))

if not SUPABASE_URL or not SUPABASE_KEY:
    logging.error("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY，請檢查 .env")
    sys.exit(1)

def _setup_smart_network():
    """
    智能雙網卡相容：
    當電腦同時接有 W610 串列網關 (10.10.100.x 無外網) 與 Wi-Fi / 外網時，
    Windows 預設路由常會被無外網的實體網線佔據，導致 Supabase HTTPS 與 DNS 查詢失敗。
    本函式自動探測可通往外網之網卡，並將雲端請求精準綁定至外網介面。
    """
    import socket
    s_test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s_test.settimeout(1.0)
    can_reach_internet = (s_test.connect_ex(('8.8.8.8', 53)) == 0)
    s_test.close()

    if can_reach_internet:
        return  # 預設網卡已能直通外網

    try:
        hostname = socket.gethostname()
        local_ips = socket.gethostbyname_ex(hostname)[2]
    except Exception:
        local_ips = []

    working_ip = None
    for ip in local_ips:
        if ip.startswith('127.') or ip.startswith('10.10.100.'):
            continue
        try:
            s_try = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s_try.bind((ip, 0))
            s_try.settimeout(1.5)
            if s_try.connect_ex(('8.8.8.8', 53)) == 0:
                working_ip = ip
                s_try.close()
                break
            s_try.close()
        except Exception:
            pass

    if not working_ip:
        return

    logging.info(f"偵測到多網卡環境，已將 Supabase 雲端連線自動路由至外網介面: {working_ip}")

    orig_create_connection = socket.create_connection
    orig_getaddrinfo = socket.getaddrinfo

    def custom_getaddrinfo(host, port, *args, **kwargs):
        if 'supabase.co' in str(host):
            for fallback_ip in ['172.64.149.246', '104.18.38.10']:
                try:
                    return orig_getaddrinfo(fallback_ip, port, *args, **kwargs)
                except Exception:
                    pass
        return orig_getaddrinfo(host, port, *args, **kwargs)

    def custom_create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
        if source_address is None and address and address[0] not in ('127.0.0.1', 'localhost'):
            source_address = (working_ip, 0)
        return orig_create_connection(address, timeout, source_address)

    socket.getaddrinfo = custom_getaddrinfo
    socket.create_connection = custom_create_connection

_setup_smart_network()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# GW1 與 GW2 全面上線：同時拉取 gw1 與 gw2 之即時狀態表
TEMP_TABLES = ['gw1_temp_status', 'gw2_temp_status']
METER_TABLES = ['gw1_meter_status', 'gw2_meter_status']


def tw_now_str():
    return datetime.now(TZ_TW).strftime('%Y-%m-%d %H:%M:%S')


def _safe(row, key, default=None):
    val = row.get(key)
    return default if val is None else val


def _to_local_ts_str(iso_str):
    """把 Supabase 回傳的 updated_at（ISO 格式，資料庫存的已是台灣本地時間）轉成
    '%Y-%m-%d %H:%M:%S' 字串，讓前端可以用『每個 channel 自己真實的更新時間』
    來判斷是否離線，而不是每次輪詢都被蓋成『現在』（那樣硬體真的斷線 3 天也會
    被誤判成上線，GW2 沒架設卻顯示假資料在線的問題就是這樣來的）"""
    if not iso_str:
        return None
    s = str(iso_str).replace('T', ' ')
    if '.' in s:
        s = s.split('.')[0]
    return s


def fetch_temp_readings():
    """讀取 gw1_temp_status / gw2_temp_status，轉成 modbus_reader.py 相同格式"""
    results = {}
    for table in TEMP_TABLES:
        try:
            resp = supabase.table(table).select('*').execute()
        except Exception as e:
            logging.error(f"讀取 {table} 失敗: {e}")
            continue

        for row in (resp.data or []):
            ch = row.get('channel')
            if not ch:
                continue

            ctrl_temp = _safe(row, 'control_temp', 0.0)
            high_alarm = bool(_safe(row, 'status_high_temp_alarm', False))
            low_alarm = bool(_safe(row, 'status_low_temp_alarm', False))

            results[ch] = {
                'name': row.get('device_name') or ch,
                'timestamp': _to_local_ts_str(row.get('updated_at')),
                'value': ctrl_temp,
                'control_temperature': ctrl_temp,
                'coil_temperature': _safe(row, 'coil_temp', 0.0),
                'compressor_current': _safe(row, 'compressor_current', 0.0),
                'high_pressure': _safe(row, 'high_pressure', 0.0),
                'low_pressure': _safe(row, 'low_pressure', 0.0),
                'control_temperature_set': _safe(row, 'set_temp', 0.0),
                'running_status': bool(_safe(row, 'status_running', False)),
                'cooling_status': bool(_safe(row, 'status_cooling', False)),
                'defrost_status': bool(_safe(row, 'status_defrost', False)),
                'fan_status': bool(_safe(row, 'status_fan', False)),
                'status': 'ALARM' if (high_alarm or low_alarm) else 'NORMAL',
                'flags': {
                    'running': bool(_safe(row, 'status_running', False)),
                    'cooling': bool(_safe(row, 'status_cooling', False)),
                    'defrost': bool(_safe(row, 'status_defrost', False)),
                    'fan': bool(_safe(row, 'status_fan', False)),
                    'eq_err': bool(_safe(row, 'status_equip_err', False)) or bool(_safe(row, 'status_overload_err', False)) or bool(_safe(row, 'status_phase_err', False)),
                    'overload_err': bool(_safe(row, 'status_overload_err', False)),
                    'phase_err': bool(_safe(row, 'status_phase_err', False)),
                    'sensor_err': bool(_safe(row, 'status_sensor_err', False)),
                    'temp_err': False,
                },
                '_source': 'supabase',
                '_updated_at': row.get('updated_at'),
            }
    return results


def fetch_meter_readings():
    """讀取 gw1_meter_status / gw2_meter_status，轉成 modbus_reader.py 相同格式
    注意單位換算：Supabase 存的 power_total 是 kW、energy_total 是 kWh (原生單位)，
    但前端 index.html 的 power.power_total / power.energy_total 欄位預期是 W / Wh
    (跟 modbus_reader.py 本機讀取時刻意 *1000 對齊)，所以這裡要做同樣的換算。
    """
    results = {}
    for table in METER_TABLES:
        try:
            resp = supabase.table(table).select('*').execute()
        except Exception as e:
            logging.error(f"讀取 {table} 失敗: {e}")
            continue

        for row in (resp.data or []):
            ch = row.get('channel')
            if not ch:
                continue

            kw = float(_safe(row, 'power_total', 0.0) or 0.0)
            kwh = float(_safe(row, 'energy_total', 0.0) or 0.0)

            results[ch] = {
                'name': row.get('device_name') or ch,
                'timestamp': _to_local_ts_str(row.get('updated_at')),
                'value': kwh,
                'unit': 'kWh',
                'power': {
                    'voltage_rs': _safe(row, 'voltage_rs', 0.0),
                    'voltage_st': _safe(row, 'voltage_st', 0.0),
                    'voltage_tr': _safe(row, 'voltage_tr', 0.0),
                    'voltage_ll_avg': _safe(row, 'voltage_avg', 0.0),
                    'frequency': _safe(row, 'frequency', 0.0),
                    'current_r': _safe(row, 'current_r', 0.0),
                    'current_s': _safe(row, 'current_s', 0.0),
                    'current_t': _safe(row, 'current_t', 0.0),
                    'current_avg': _safe(row, 'current_avg', 0.0),
                    'power_total': round(kw * 1000.0, 1),   # W
                    'kw': kw,                                 # kW (原生)
                    'power_factor': _safe(row, 'power_factor', 0.0),
                    'energy_total': round(kwh * 1000.0, 1), # Wh
                    'kwh': kwh,                                # kWh (原生)
                },
                '_source': 'supabase',
                '_updated_at': row.get('updated_at'),
            }
    return results


def publish_to_backend(readings, persist=False):
    """persist=False：只更新畫面即時快取 (realtime_only)
    persist=True：同時寫入本機季度 DB (與 modbus_reader.py 一致，每分鐘存一次)
    """
    if not readings:
        return False
    payload = {
        'timestamp': tw_now_str(),
        'readings': readings,
        'realtime_only': not persist,
        '_source': 'supabase'   # 來源標籤：讓 app.py 知道這是 Supabase 補位資料
    }
    try:
        resp = requests.post(f'{API_BASE}/api/temperatures', json=payload, timeout=5)
        if resp.status_code == 200:
            tag = '即時快取+寫入DB' if persist else '即時快取'
            logging.info(f"✓ 已推送 {len(readings)} 筆 ({tag}, 來源: Supabase) -> {API_BASE}")
            return True
        logging.error(f"推送失敗 HTTP {resp.status_code}: {resp.text}")
    except requests.exceptions.ConnectionError:
        logging.error(f"無法連線到本機後端 {API_BASE}，請確認 local_web/app.py 是否已啟動")
    except Exception as e:
        logging.error(f"推送失敗: {e}")
    return False


def fetch_diagnostic_status():
    """從 Supabase 拉取 gateway_status 與 device_status 診斷資訊"""
    gw_data = []
    dev_data = []
    try:
        r = supabase.table('gateway_status').select('*').execute()
        if r and r.data:
            gw_data = r.data
    except Exception:
        pass

    try:
        r = supabase.table('device_status').select('*').execute()
        if r and r.data:
            dev_data = r.data
    except Exception:
        pass

    return gw_data, dev_data


def publish_diagnostics(gw_data, dev_data):
    """將診斷資料轉發至本機 local_web API 端點"""
    if gw_data:
        try:
            requests.post(f'{API_BASE}/api/gateway_status', json=gw_data, timeout=3)
        except Exception:
            pass
    if dev_data:
        try:
            requests.post(f'{API_BASE}/api/device_status', json=dev_data, timeout=3)
        except Exception:
            pass


def sync_cloud_configs_to_backend():
    """從 Supabase 拉取 system_config, room_alarm_settings 與 alarm_settings 並同步至本地端點"""
    try:
        r_sys = supabase.table('system_config').select('*').execute()
        r_rooms = supabase.table('room_alarm_settings').select('*').execute()
        r_alarms = None
        try:
            r_alarms = supabase.table('alarm_settings').select('*').execute()
        except Exception:
            pass

        sys_data = r_sys.data if r_sys and r_sys.data else []
        room_data = r_rooms.data if r_rooms and r_rooms.data else []
        alarm_data = r_alarms.data if r_alarms and r_alarms.data else []

        if sys_data or room_data or alarm_data:
            resp = requests.post(f'{API_BASE}/api/sync_cloud_config', json={
                'system_config': sys_data,
                'room_alarm_settings': room_data,
                'alarm_settings': alarm_data
            }, timeout=5)
            if resp.status_code == 200:
                res = resp.json()
                logging.info(f"⚙️ 雲端設定同步完成 (系統設定: {res.get('updated_system_config', 0)} 筆, 庫房門檻: {res.get('updated_room_settings', 0)} 筆)")
    except Exception as e:
        logging.debug(f"雲端設定同步暫未完成: {e}")


def main():
    logging.info("=" * 72)
    logging.info("🌉 臨時資料橋接啟動：Supabase 即時狀態 → 本機 /api/temperatures")
    logging.info(f"   Supabase: {SUPABASE_URL}")
    logging.info(f"   本機 API: {API_BASE}")
    logging.info(f"   輪詢間隔: {POLL_INTERVAL} 秒（即時快取）／ 60 秒（寫入本機 DB）")
    logging.info("   注意：此為過渡方案，Supabase 來源本身僅有『最新狀態』")
    logging.info("         本機 DB 會依實際輪詢頻率累積歷史，供之後查詢/報表使用")
    logging.info("   GW2 IP 確認、現場可連線後，請改跑 collector/modbus_reader.py")
    logging.info("=" * 72)

    last_saved_minute = None
    CONFIG_SYNC_INTERVAL = 15.0  # 每 15 秒同步一次雲端設定
    last_config_sync = 0

    while True:
        try:
            readings = {}
            readings.update(fetch_temp_readings())
            readings.update(fetch_meter_readings())

            if readings:
                now = datetime.now(TZ_TW)
                current_minute = now.strftime('%Y-%m-%d %H:%M')
                should_persist = (current_minute != last_saved_minute)
                if publish_to_backend(readings, persist=should_persist) and should_persist:
                    last_saved_minute = current_minute
            else:
                logging.warning("本輪未取得任何 Supabase 資料")

            # 同步拉取並轉發網關與設備連線診斷狀態
            gw_data, dev_data = fetch_diagnostic_status()
            publish_diagnostics(gw_data, dev_data)

            # 每 15 秒同步一次雲端設定 (system_config 與 room_alarm_settings)
            now_ts = time.time()
            if now_ts - last_config_sync >= CONFIG_SYNC_INTERVAL:
                sync_cloud_configs_to_backend()
                last_config_sync = now_ts

        except KeyboardInterrupt:
            raise
        except Exception as e:
            logging.error(f"橋接迴圈發生未預期錯誤: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logging.info("\n使用者中斷，停止橋接服務。")
