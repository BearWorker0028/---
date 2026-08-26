import time
import logging
import requests
import os
import json
from datetime import datetime, timezone, timedelta
from pymodbus.client import ModbusTcpClient
from pymodbus.framer import FramerType

try:
    import psycopg
except ImportError:
    psycopg = None

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '..', '.env'))
CHANNEL_CONFIG_PATH = os.getenv(
    'CHANNEL_CONFIG_PATH',
    os.path.join(BASE_DIR, 'channel_config.json')
)
CHANNEL_CONFIG_EXAMPLE_PATH = os.path.join(BASE_DIR, 'channel_config.example.json')

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if not DATABASE_URL:
    logging.warning(
        'DATABASE_URL 未設定，將僅推送資料至 API，不寫入資料庫。'
        '若需存儲歷史資料，請在 .env 設定 DATABASE_URL。'
    )

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

DEFAULT_CHANNEL_CONFIG = {
    'ch01': {'reg': 0, 'slave': 1, 'name': '成品庫',      'enabled': True},
    'ch02': {'reg': 1, 'slave': 1, 'name': '急速庫16HP',  'enabled': True},
    'ch03': {'reg': 2, 'slave': 1, 'name': '冷藏庫(小)',  'enabled': True},
    'ch04': {'reg': 3, 'slave': 1, 'name': '冷藏庫(大)',  'enabled': True},
    'ch05': {'reg': 4, 'slave': 1, 'name': '原料庫',      'enabled': True},
    'ch06': {'reg': 5, 'slave': 1, 'name': '急速庫10HP',  'enabled': True},
    'ch07': {'reg': 0, 'slave': 2, 'name': '處理室',      'enabled': True},
    'ch08': {'reg': 1, 'slave': 2, 'name': '儲冰桶',      'enabled': True},
    'ch09': {'reg': 2, 'slave': 2, 'name': '儲熱桶',      'enabled': True},
    'ch10': {'reg': 3, 'slave': 2, 'name': '機房',        'enabled': True},
    'ch11': {'reg': 4, 'slave': 2, 'name': '電器室',      'enabled': True},
    'ch12': {'reg': 5, 'slave': 2, 'name': '電腦室',      'enabled': True},
}

def _normalize_channel_config(raw_config):
    channels = raw_config.get('channels', []) if isinstance(raw_config, dict) else []
    normalized = {}
    for item in channels:
        if not isinstance(item, dict):
            continue
        ch = item.get('channel')
        if not ch:
            continue
        normalized[ch] = {
            'reg': int(item.get('reg', item.get('register', 0))),
            'slave': int(item.get('slave', 1)),
            'name': item.get('name') or ch,
            'gateway': item.get('gateway', 'GW1'),
            'enabled': bool(item.get('enabled', True)),
            'scale': float(item.get('scale', 0.1)),
            'offset': float(item.get('offset', 0.0)),
            'data_type': item.get('data_type', 'int16'),
            'device_type': item.get('device_type', 'iot627'),
            'invalid_below': item.get('invalid_below', -199.0),
        }
    return normalized

def _load_channel_config():
    for path in (CHANNEL_CONFIG_PATH, CHANNEL_CONFIG_EXAMPLE_PATH):
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            channels = _normalize_channel_config(raw)
            if channels:
                logging.info(f"已載入通道設定：{path}")
                return raw, channels
        except Exception as e:
            logging.error(f"載入通道設定失敗 {path}: {e}")
    return {}, DEFAULT_CHANNEL_CONFIG

SITE_CONFIG_RAW, CHANNEL_CONFIG = _load_channel_config()

# ── 多 Gateway 設定解析（向下相容舊的單一 modbus 區塊）──────────────
def _parse_gateway_config(raw):
    """從 config 解析 gateway 連線資訊，支援新舊兩種格式"""
    if not isinstance(raw, dict):
        return {}
    # 新格式：gateways 字典
    gateways = raw.get('gateways')
    if gateways and isinstance(gateways, dict):
        result = {}
        for gw_id, gw_cfg in gateways.items():
            result[gw_id] = {
                'host': str(gw_cfg.get('host', '192.168.x.x')),
                'port': int(gw_cfg.get('port', 2000)),
                'framer': str(gw_cfg.get('framer', 'RTU_OVER_TCP')),
                'description': str(gw_cfg.get('description', '')),
            }
        logging.info(f"已載入 {len(result)} 組 Gateway 設定: {list(result.keys())}")
        return result
    # 舊格式：單一 modbus 區塊 → 轉為 GW1
    modbus = raw.get('modbus', {})
    if modbus:
        logging.info("使用舊格式 modbus 設定，自動轉為 GW1")
        return {
            'GW1': {
                'host': str(modbus.get('host', '192.168.x.x')),
                'port': int(modbus.get('port', 2000)),
                'framer': str(modbus.get('framer', 'RTU_OVER_TCP')),
                'description': 'Legacy single gateway',
            }
        }
    return {}

GATEWAY_CONFIG = _parse_gateway_config(SITE_CONFIG_RAW)

API_BASE      = os.getenv('API_BASE', 'http://127.0.0.1:88').rstrip('/')
PUBLISH_TO_API = os.getenv('PUBLISH_TO_API', '0').lower() in ('1', 'true', 'yes', 'on')
ALARM_COOLDOWN = 600  # 秒，同通道同類型間隔 10 分鐘才再次記錄

# Pushover 設定
PUSHOVER_TOKEN = os.getenv('PUSHOVER_TOKEN', '')
PUSHOVER_USER  = os.getenv('PUSHOVER_USER', '')

def send_pushover(title, message):
    if not PUSHOVER_TOKEN or not PUSHOVER_USER:
        logging.warning("Pushover Token/User 未設定，跳過推播")
        return
    try:
        resp = requests.post("https://api.pushover.net/1/messages.json", data={
            "token":   PUSHOVER_TOKEN,
            "user":    PUSHOVER_USER,
            "title":   title,
            "message": message
        }, timeout=5)
        if resp.status_code == 200:
            logging.info(f"Pushover 推播發送成功: {title}")
        else:
            logging.error(f"Pushover 回應異常 HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logging.error(f"Pushover 發送失敗: {e}")
last_alarm_time = {}
violation_start_time = {}

TZ_TW = timezone(timedelta(hours=8))

# ─────────────────────────────────────────────────────────────

def signed_int16(raw):
    return raw - 65536 if raw > 32767 else raw

def to_unsigned_int16(value):
    """有號整數轉為 Modbus 寫入用的 16-bit 補碼表示"""
    return int(value) & 0xFFFF

def tw_now():
    """取得台灣時間字串"""
    return datetime.now(TZ_TW).strftime('%Y-%m-%d %H:%M:%S')

ROOM_CONFIG = {
    'room1': {'name': '1F 冷凍庫', 'channels': ['ch01', 'ch02', 'ch03', 'ch04', 'ch05']},
    'room2': {'name': '1F 緩衝庫', 'channels': ['ch06']},
    'room3': {'name': '1F 碼頭區', 'channels': ['ch07']},
    'room4': {'name': '3F 急速庫', 'channels': ['ch08', 'ch09']},
    'room5': {'name': '3F 半成品冷凍庫', 'channels': ['ch10', 'ch11']},
    'room6': {'name': '3F 冷藏庫', 'channels': ['ch12']},
}

def get_room_alarm_settings():
    res = {}
    try:
        r = requests.get(f'{API_BASE}/api/room_alarm_settings', timeout=3)
        if r.ok:
            res = r.json()
    except Exception as e:
        logging.error(f"取得庫別警報設定失敗: {e}")
    try:
        rc = requests.get(f'{API_BASE}/api/system_config', timeout=3)
        if rc.ok:
            res['_config'] = rc.json()
    except Exception:
        pass
    return res

def check_and_log_room_alarms(data, room_settings):
    """依「庫別平均庫溫」進行警報判定，避免單一機組除霜或短暫跳動造成誤報"""
    now = time.time()
    room_statuses = {}

    for room_id, r_cfg in ROOM_CONFIG.items():
        s = room_settings.get(room_id)
        if not s:
            room_statuses[room_id] = 'NORMAL'
            continue

        # 庫別溫度校正
        offset = float(s.get('temp_offset', 0.0) or 0.0)

        # 計算該庫別所有在線設備的有效溫度
        valid_temps = []
        for ch in r_cfg['channels']:
            if ch in data and data[ch].get('value') is not None:
                val = float(data[ch]['value'])
                if offset != 0.0:
                    val = round(val + offset, 1)
                    data[ch]['value'] = val
                valid_temps.append(val)

        if not valid_temps:
            room_statuses[room_id] = 'OFFLINE'
            continue

        # 庫別平均庫溫
        room_avg = round(sum(valid_temps) / len(valid_temps), 1)

        # 警報總開關
        if not int(s.get('alarm_enabled', 1)):
            if room_id in violation_start_time:
                del violation_start_time[room_id]
            room_statuses[room_id] = 'NORMAL'
            continue

        hi = s.get('hi')
        lo = s.get('lo')
        delay_minutes = int(s.get('delay', 0) or 0)
        alarm_type = None

        if hi is not None and room_avg > hi:
            alarm_type = 'HIGH'
        elif lo is not None and room_avg < lo:
            alarm_type = 'LOW'

        if not alarm_type:
            if room_id in violation_start_time:
                del violation_start_time[room_id]
                for key in [f'{room_id}_HIGH', f'{room_id}_LOW']:
                    if key in last_alarm_time:
                        del last_alarm_time[key]
                logging.info(f"{r_cfg['name']} 平均庫溫恢復正常 ({room_avg}°C)，警報狀態已重置")
            room_statuses[room_id] = 'NORMAL'
            continue

        if room_id not in violation_start_time:
            violation_start_time[room_id] = now

        elapsed_minutes = (now - violation_start_time[room_id]) / 60.0
        if elapsed_minutes < delay_minutes:
            room_statuses[room_id] = 'DELAYING'
            continue

        key = f'{room_id}_{alarm_type}'
        last_t = last_alarm_time.get(key, 0)
        cooldown = ALARM_COOLDOWN
        if isinstance(room_settings, dict) and '_config' in room_settings:
            cooldown = int(room_settings['_config'].get('push_cooldown_min', 10)) * 60

        room_statuses[room_id] = 'TRIGGERED'

        if now - last_t < cooldown:
            continue

        try:
            requests.post(f'{API_BASE}/api/alarm_history', json={
                'channel':    room_id,
                'name':       r_cfg['name'],
                'value':      room_avg,
                'alarm_type': alarm_type,
                'hi':         hi,
                'lo':         lo
            }, timeout=3)
            
            # 發送 Pushover / LINE 推播通知
            msg = f"庫別: {r_cfg['name']}\n目前平均庫溫: {room_avg}°C\n警報類型: {'🔴 高溫超標' if alarm_type=='HIGH' else '🔵 低溫超標'}\n設定門檻: {hi if alarm_type=='HIGH' else lo}°C (持續 > {delay_minutes}分)"
            send_pushover("⚠️ 庫溫異常預警通知", msg)

            last_alarm_time[key] = now
            logging.warning(
                f"警報發布! {r_cfg['name']} 平均庫溫: {room_avg}°C "
                f"({'高溫 hi='+str(hi) if alarm_type=='HIGH' else '低溫 lo='+str(lo)})"
            )
        except Exception as e:
            logging.error(f"發送警報歷史或推播失敗: {e}")

    # 將庫別狀態同步標註到各機組通道上
    for room_id, r_cfg in ROOM_CONFIG.items():
        st = room_statuses.get(room_id, 'NORMAL')
        for ch in r_cfg['channels']:
            if ch in data:
                data[ch]['status'] = st
                data[ch]['in_alarm'] = (st == 'TRIGGERED')
                data[ch]['room_status'] = st

    return room_statuses

def raw_to_temp(raw, cfg=None):
    cfg = cfg or {}
    data_type = str(cfg.get('data_type', 'int16')).lower()
    if data_type in ('int16', 'signed_int16') and raw > 32767:
        raw = raw - 65536
    scale = float(cfg.get('scale', 0.1))
    offset = float(cfg.get('offset', 0.0))
    temp = raw * scale + offset
    invalid_below = cfg.get('invalid_below', -199.0)
    if invalid_below is not None and temp <= float(invalid_below):
        return None
    return temp



def read_all_channels():
    from collections import defaultdict

    results = {}

    # ── 按 gateway 分組 ─────────────────────────────────────────
    gw_channels = defaultdict(lambda: defaultdict(dict))  # gw_id -> slave_id -> {ch: cfg}
    for ch, cfg in CHANNEL_CONFIG.items():
        if cfg.get('enabled', False):
            gw_id = cfg.get('gateway', 'GW1')
            slave_id = cfg.get('slave', 1)
            gw_channels[gw_id][slave_id][ch] = cfg

    # ── 逐 gateway 連線讀取 ─────────────────────────────────────
    for gw_id, slaves in gw_channels.items():
        gw_cfg = GATEWAY_CONFIG.get(gw_id)
        if not gw_cfg:
            logging.error(f"Gateway {gw_id} 未在設定中定義，跳過")
            continue

        host = gw_cfg['host']
        port = gw_cfg['port']

        # 嘗試以 ModbusTcpClient 或 USB Serial 通訊
        client = None
        is_serial = False

        if host.startswith('COM') or host == '192.168.1.x':
            # 優先使用 USB Serial 介面 (如插著 USB COM4 測試)
            com_port = os.getenv('RS485_PORT', 'COM4')
            try:
                from pymodbus.client import ModbusSerialClient
                client = ModbusSerialClient(
                    port=com_port,
                    framer=FramerType.RTU,
                    baudrate=9600,
                    parity='N',
                    stopbits=1,
                    bytesize=8,
                    timeout=1
                )
                if client.connect():
                    is_serial = True
                    logging.info(f"[{gw_id}] 已透過 USB Serial {com_port} 開啟 RS485 通訊")
                else:
                    client = None
            except Exception as se:
                logging.warning(f"[{gw_id}] USB Serial 連線失敗: {se}")

        if not client:
            client = ModbusTcpClient(
                host,
                port=port,
                framer=FramerType.RTU
            )
            if not client.connect():
                logging.error(f"[{gw_id}] Gateway ({host}:{port}) 連線失敗")
                continue

        try:
            for slave_id, channels in slaves.items():
                if not channels:
                    continue
                try:
                    # 分開處理 IOT-627 (Holding Regs) 與 SPM-3 (Input Regs Float32)
                    for ch, cfg in channels.items():
                        device_type = cfg.get('device_type', 'iot627')
                        data_type = cfg.get('data_type', 'int16')

                        if device_type == 'spm3' or data_type == 'float32':
                            # SPM-3 使用 Function Code 04 讀取完整電力參數 (1032~1084 & 1182)
                            resp_p = client.read_input_registers(address=1032, count=52, device_id=slave_id)
                            resp_kwh = client.read_input_registers(address=1182, count=2, device_id=slave_id)
                            
                            kwh_val = 0.0
                            power_dict = {}

                            import struct
                            def _unp_f(r_a, r_b):
                                return round(struct.unpack('>f', struct.pack('>HH', r_b, r_a))[0], 2)

                            if not resp_kwh.isError() and len(resp_kwh.registers) >= 2:
                                r0, r1 = resp_kwh.registers[0], resp_kwh.registers[1]
                                kwh_val = _unp_f(r0, r1)

                            if not resp_p.isError() and len(resp_p.registers) >= 52:
                                rp = resp_p.registers
                                # 依現場實測原始暫存器反推驗證過的正確 index（讀取起點=1032，
                                # 故 index = 絕對offset(以1030為基準) - 2）：
                                # I_a+I_b+I_c 平均 = I_avg（誤差0）、kW_a+kW_b+kW_c = kW_total（誤差0），
                                # 用這個「總和=分量相加」完全吻合驗證出正確位置。
                                # 舊版 index (20/22/24/28/42) 其實讀到的是 kW_a/b/c 與 kVA_total，
                                # 被誤標成電流/實功率，導致電流與功率公式對不起來。
                                power_dict = {
                                    'voltage_rs': _unp_f(rp[0], rp[1]),
                                    'voltage_st': _unp_f(rp[2], rp[3]),
                                    'voltage_tr': _unp_f(rp[4], rp[5]),
                                    'voltage_ll_avg': _unp_f(rp[6], rp[7]),
                                    'frequency': _unp_f(rp[18], rp[19]),
                                    'current_r': _unp_f(rp[8], rp[9]),
                                    'current_s': _unp_f(rp[10], rp[11]),
                                    'current_t': _unp_f(rp[12], rp[13]),
                                    'current_avg': _unp_f(rp[14], rp[15]),
                                    'power_total': round(_unp_f(rp[26], rp[27]) * 1000.0, 1), # W
                                    'kw': _unp_f(rp[26], rp[27]),                              # kW
                                    'power_factor': _unp_f(rp[50], rp[51]),
                                    'reactive_power': _unp_f(rp[34], rp[35]),                  # kvar
                                    'apparent_power': _unp_f(rp[42], rp[43]),                  # kVA
                                    'energy_total': round(kwh_val * 1000.0, 1),              # Wh
                                    'kwh': kwh_val                                           # kWh
                                }

                            results[ch] = {
                                'name': cfg['name'],
                                'value': kwh_val,
                                'unit': 'kWh',
                                'power': power_dict
                            }
                            logging.info(f"[{gw_id}] Slave {slave_id} (SPM-3) - {ch} {cfg['name']}: {kwh_val} kWh | {power_dict.get('kw', 0)} kW")

                        else:
                            # IOT-627 依據範本抓取 10 大核心點位
                            # 1. 讀取 Offset 6 (Modicon 40007): 設定溫度 control_temperature_set
                            resp_set = client.read_holding_registers(address=6, count=1, device_id=slave_id)
                            set_temp = 0.0
                            if not resp_set.isError() and len(resp_set.registers) > 0:
                                set_temp = round(signed_int16(resp_set.registers[0]) * 0.1, 1)

                            # 2. 讀取 Offset 34~47 (Modicon 40035~40048)
                            response = client.read_holding_registers(address=34, count=14, device_id=slave_id)
                            if not response.isError() and len(response.registers) >= 14:
                                r = response.registers
                                status_raw = r[0]
                                bits = [(status_raw >> i) & 1 for i in range(16)]

                                ctrl_temp  = round(signed_int16(r[5]) * 0.1, 1)  # Offset 39 (40040) 控制溫度
                                coil_temp  = round(signed_int16(r[6]) * 0.1, 1)  # Offset 40 (40041) 盤管溫度
                                low_press  = round(signed_int16(r[8]) * 0.1, 1)  # Offset 42 (40043) 低壓壓力
                                high_press = round(r[10] * 0.1, 1)              # Offset 44 (40045) 高壓壓力
                                comp_curr  = round(signed_int16(r[12]) * 0.1, 1) # Offset 46 (40047) 運轉電流

                                results[ch] = {
                                    'name': cfg['name'],
                                    'value': ctrl_temp,                 # 控制溫度 L301
                                    'control_temperature': ctrl_temp,   # 控制溫度 L301 (40040)
                                    'coil_temperature': coil_temp,      # 盤管溫度 L302 (40041)
                                    'compressor_current': comp_curr,    # 運轉電流 L306 (40047)
                                    'high_pressure': high_press,        # 高壓壓力 L305 (40045)
                                    'low_pressure': low_press,          # 低壓壓力 L304 (40043)
                                    'control_temperature_set': set_temp,# 設定溫度 L101 (40007)
                                    'running_status': bool(bits[0]),    # 運轉 L201 (40035 bit 0)
                                    'cooling_status': bool(bits[8]),    # 製冷 L209 (40035 bit 8)
                                    'defrost_status': bool(bits[1]),    # 除霜 L202 (40035 bit 1)
                                    'fan_status': bool(bits[7]),        # 風機 L208 (40035 bit 7)
                                    'status': 'NORMAL',
                                    'flags': {
                                        'running': bool(bits[0]),
                                        'cooling': bool(bits[8]),
                                        'defrost': bool(bits[1]),
                                        'fan': bool(bits[7]),
                                        'eq_err': False,
                                        'temp_err': False
                                    }
                                }
                                logging.info(
                                    f"[{gw_id}] Slave {slave_id} (IoT627) - {ch} {cfg['name']}: "
                                    f"控溫={ctrl_temp}°C, 盤管={coil_temp}°C, 電流={comp_curr}A, 高壓={high_press}bar, 低壓={low_press}bar"
                                )
                            else:
                                logging.error(f"[{gw_id}] Slave {slave_id} - {ch} 讀取錯誤: {response}")
                except Exception as e:
                    logging.error(f"[{gw_id}] 模組 {slave_id} 讀取發生未預期錯誤: {e}")
        except Exception as e:
            logging.error(f"[{gw_id}] 準備讀取參數時發生錯誤: {e}")
        finally:
            if client:
                client.close()

    return results if results else None

# ── 設備控制命令：向後端取待執行命令、寫入 Modbus、回報結果 ─────────────
# 依 IoT627_RS485通信點位表.xlsx：控制溫度設定 (L101) = offset 6, FC06, int16, scale 0.1, degC
# 依 IoT627_完整掃描點位表_220點.csv（現場實測 100% 確認）：
#   A801 停控模式 = offset 178（40179），uint16，0=全停 1=全開 2=只出Triac1 3=只出DO3
#   本系統只用 0/1 兩種狀態，對應前端「設備起停」開關
CONTROL_TEMPERATURE_SET_OFFSET = 6
STOP_CONTROL_MODE_OFFSET = 178

def _write_single_register(ch, register_offset, raw_value):
    """寫入 IoT627 單一 holding register (FC=06)。回傳 (success, error_message)。"""
    cfg = CHANNEL_CONFIG.get(ch)
    if not cfg or not cfg.get('enabled', False):
        return False, f'通道 {ch} 未設定或未啟用'

    gw_id = cfg.get('gateway', 'GW1')
    slave_id = cfg.get('slave', 1)
    gw_cfg = GATEWAY_CONFIG.get(gw_id)
    if not gw_cfg:
        return False, f'Gateway {gw_id} 未在設定中定義'

    host = gw_cfg['host']
    port = gw_cfg['port']

    client = ModbusTcpClient(host, port=port, framer=FramerType.RTU)
    if not client.connect():
        return False, f'[{gw_id}] Gateway ({host}:{port}) 連線失敗'

    try:
        resp = client.write_register(address=register_offset, value=to_unsigned_int16(raw_value), device_id=slave_id)
        if resp.isError():
            return False, f'寫入失敗: {resp}'
        return True, None
    except Exception as e:
        return False, f'寫入發生例外: {e}'
    finally:
        client.close()

def write_temperature_setpoint(ch, target_temp):
    """寫入 IoT627 控制溫度設定。回傳 (success, error_message)。"""
    raw_value = round(target_temp * 10)
    success, error = _write_single_register(ch, CONTROL_TEMPERATURE_SET_OFFSET, raw_value)
    if success:
        logging.info(f"[{ch}] 控制溫度設定已寫入: {target_temp}°C (raw={raw_value})")
    return success, error

def write_power_state(ch, on):
    """寫入 IoT627 停控模式 (A801)：on=True 全開(1)，on=False 全停(0)。回傳 (success, error_message)。"""
    raw_value = 1 if on else 0
    success, error = _write_single_register(ch, STOP_CONTROL_MODE_OFFSET, raw_value)
    if success:
        logging.info(f"[{ch}] 停控模式(A801)已寫入: {'開' if on else '停'}")
    return success, error

def poll_and_execute_commands():
    """向後端取 pending 命令，逐一執行並回報結果"""
    try:
        resp = requests.get(f'{API_BASE}/api/device_commands', params={'status': 'pending', 'limit': 20}, timeout=5)
        commands = resp.json()
    except Exception as e:
        logging.error(f"取得待執行命令失敗: {e}")
        return

    for cmd in commands:
        cmd_id = cmd['id']
        ch = cmd['channel']
        cmd_type = cmd['command_type']

        if cmd_type == 'set_temperature':
            success, error = write_temperature_setpoint(ch, cmd['value'])
        elif cmd_type == 'set_power_state':
            success, error = write_power_state(ch, float(cmd['value']) == 1)
        else:
            success, error = False, f'不支援的命令類型: {cmd_type}'

        if not success:
            logging.error(f"命令執行失敗 (id={cmd_id}, ch={ch}, type={cmd_type}): {error}")

        try:
            requests.post(
                f'{API_BASE}/api/device_commands/{cmd_id}/complete',
                json={'success': success, 'error_message': error},
                timeout=5
            )
        except Exception as e:
            logging.error(f"回報命令結果失敗 (id={cmd_id}): {e}")

def save_to_postgres(data, timestamp: str):
    if not psycopg:
        logging.error("psycopg 未安裝，無法寫入 PostgreSQL")
        return
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                for ch, info in data.items():
                    cursor.execute(
                        'INSERT INTO temperatures (timestamp, channel, name, value, status) '
                        'VALUES (%s, %s, %s, %s, %s)',
                        (timestamp, ch, info['name'], float(info['value']),
                         info.get('status', 'NORMAL'))
                    )
        logging.info(f"已儲存 {len(data)} 筆資料至 Supabase ({timestamp})")
    except Exception as e:
        logging.error(f"Supabase 寫入失敗: {e}")

def publish_to_backend(data):
    if not PUBLISH_TO_API:
        return
    try:
        payload = {
            'timestamp': tw_now(),
            'readings': data,
            'realtime_only': True,
            '_source': 'modbus'   # 來源標籤：讓 app.py 優先使用 Modbus 資料
        }
        resp = requests.post(f'{API_BASE}/api/temperatures', json=payload, timeout=5)
        if resp.status_code == 200:
            logging.info(f"Published {len(data)} readings to backend [source=modbus]")
        else:
            logging.error(f"Publish failed HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logging.error(f"Publish failed: {e}")

if __name__ == '__main__':
    logging.info("溫度監控啟動 (Pt100 模式 / 台灣時間)")

    last_saved_minute = None

    while True:
        room_settings = get_room_alarm_settings()
        data = read_all_channels()
        if data:
            check_and_log_room_alarms(data, room_settings)
            publish_to_backend(data)

            # 每分鐘只寫入 DB 一次
            now = datetime.now(TZ_TW)
            current_minute = now.strftime('%Y-%m-%d %H:%M')
            if current_minute != last_saved_minute:
                ts = now.strftime('%Y-%m-%d %H:%M:%S')
                if DATABASE_URL:
                    save_to_postgres(data, ts)
                last_saved_minute = current_minute
        else:
            logging.error("本次讀取無有效資料")

        poll_and_execute_commands()

        time.sleep(2)
