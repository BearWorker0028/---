# -*- coding: utf-8 -*-
"""
GCP 雲端專用：W610 Modbus TCP 閘道輪詢服務 (TCP Server 模式) - Supabase 版本
- 部署於 GCP 雲端伺服器 (Cloud VM) 執行
- GCP 開啟 TCP Server，等待案場 W610 (TCP Client) 主動連入
- W610 設定為 "Modbus TCP <=> Modbus RTU" 閘道模式
- GCP 透過 Modbus TCP 格式輪詢 IoT-627 (溫控) 與 SPM-3 (電錶)
- 將資料寫入 Supabase 資料庫 (gw1_telemetry)
"""

import sys
import time
import json
import struct
import socket
import threading
import queue
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from supabase import create_client, Client

TAIWAN_TZ = ZoneInfo("Asia/Taipei")

def now_taiwan_str():
    """回傳台灣本地時間字串 (供寫入 TIMESTAMP 欄位使用)"""
    return datetime.now(TAIWAN_TZ).strftime('%Y-%m-%d %H:%M:%S')

# 設定 Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ── 0. Supabase & 環境變數設定 ──
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logging.error("Missing SUPABASE_URL or SUPABASE_KEY in .env file.")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TEMP_TABLE = "gw2_temp_status"     # IoT-627 溫控器
METER_TABLE = "gw2_meter_status"   # SPM-3 電表

# 建立背景寫入 Queue (避免網路延遲阻塞 Modbus 輪詢)
db_queue = queue.Queue()

# ── 1. 系統與通訊設定 ──
TCP_SERVER_PORT = 1883              # GCP 開放的 TCP Server Port

POLL_INTERVAL_BETWEEN_DEVICES = 0.3  # 每次讀取不同設備之間的延遲 (秒)
POLL_INTERVAL_BATCH = 3.0            # 每輪掃描完畢後的延遲 (秒)
RESPONSE_TIMEOUT = 3.0               # 等待 W610 回傳的 Timeout 時間 (秒)
MAX_FULL_CYCLE_FAILURES = 3          # 連續幾輪全部設備都無回應，就判定連線靜默失效並強制重連

DEVICES = [
    {"ch": "ch10", "id": 11, "type": "IoT-627", "name": "3F 半成品冷凍 A"},
    {"ch": "ch11", "id": 12, "type": "IoT-627", "name": "3F 半成品冷凍 B"},
    {"ch": "ch08", "id": 13, "type": "IoT-627", "name": "3F 急速庫 20HP"},
    {"ch": "ch09", "id": 14, "type": "IoT-627", "name": "3F 急速庫 10HP"},
    {"ch": "ch12", "id": 15, "type": "IoT-627", "name": "3F 冷藏庫"},
    {"ch": "ch14", "id": 16, "type": "SPM-3",   "name": "3F 集合式電錶"},
]

# ── 2. 背景寫入 Supabase Worker ──
def supabase_worker():
    """背景執行緒：處理資料庫寫入 (Upsert)"""
    logging.info("🚀 Supabase 背景寫入執行緒已啟動 (Realtime Upsert Mode)")
    while True:
        try:
            payload = db_queue.get()
            if payload is None:
                break
                
            table_name = payload.pop("_table", None)
            try:
                # 寫入 Supabase (使用 Upsert 更新最新狀態)
                supabase.table(table_name).upsert(payload).execute()
                logging.debug(f"✅ 成功更新狀態至 Supabase [{table_name}]: {payload['channel']}")
            except Exception as e:
                logging.error(f"❌ Supabase 狀態更新失敗 [{table_name}]: {e}")
                
            db_queue.task_done()
        except Exception as e:
            logging.error(f"⚠️ Worker 發生未預期錯誤: {e}")

# ── 3. Modbus TCP 通訊函式 ──
# 對應 W610「TCP Server + Modbus RTU over TCP」閘道模式（與 GW1 相同），
# W610 會負責 Modbus TCP (MBAP) <-> RTU (含 CRC) 的協定轉換，GCP 端只需送標準 Modbus TCP 封包。
trans_id_counter = 0

def next_trans_id():
    """產生遞增的 Transaction ID"""
    global trans_id_counter
    trans_id_counter = (trans_id_counter + 1) % 65536
    return trans_id_counter

class ConnectionDeadError(Exception):
    """連線已確定失效 (對方關閉/送出 RST)，需捨棄此連線並等待 W610 重新連入"""
    pass

def send_modbus_tcp_request(conn, slave_id, function_code, start_addr, reg_count):
    """
    發送 Modbus TCP 請求並等待回應
    回傳: tuple of registers (成功) 或 None (單純逾時，連線仍視為存活)
    連線確定失效時拋出 ConnectionDeadError，讓上層捨棄連線並重新等待 W610 連入
    """
    tid = next_trans_id()

    # 建立 Modbus TCP 封包 (MBAP Header + PDU，不需要 CRC)
    pdu = struct.pack('>BBHH', slave_id, function_code, start_addr, reg_count)
    mbap = struct.pack('>HHH', tid, 0x0000, len(pdu))
    request = mbap + pdu

    try:
        conn.sendall(request)
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        raise ConnectionDeadError(f"傳送失敗: {e}")

    # 接收回應
    try:
        header = b''
        while len(header) < 6:
            chunk = conn.recv(6 - len(header))
            if not chunk:
                # recv 回傳空值代表對方已關閉連線 (EOF)，並非逾時
                raise ConnectionDeadError("連線已被對方關閉 (EOF)")
            header += chunk

        resp_tid, resp_proto, resp_len = struct.unpack('>HHH', header)

        body = b''
        while len(body) < resp_len:
            chunk = conn.recv(resp_len - len(body))
            if not chunk:
                raise ConnectionDeadError("連線已被對方關閉 (EOF)")
            body += chunk

        resp_unit_id = body[0]
        resp_fc = body[1]

        if resp_fc >= 0x80:
            error_code = body[2]
            logging.warning(f"Slave {resp_unit_id} 回傳 Modbus 錯誤碼: {error_code}")
            return None

        byte_count = body[2]
        data = body[3:3+byte_count]

        reg_count_actual = byte_count // 2
        regs = struct.unpack(f'>{reg_count_actual}H', data)
        return regs

    except socket.timeout:
        return None
    except ConnectionDeadError:
        raise
    except Exception as e:
        logging.error(f"接收回應時發生錯誤: {e}")
        return None

# ── 4. 資料解碼函式 ──
def to_signed(raw):
    """將無號 16-bit 轉成有號整數"""
    return raw - 65536 if raw > 32767 else raw

# ── 5. 主程式邏輯 ──
def handle_w610_connection(conn, addr):
    """處理一個 W610 的連線：持續輪詢設備並寫入 Queue"""
    logging.info(f"🔗 W610 已連入！來源: {addr[0]}:{addr[1]}")
    logging.info("開始自動輪詢並轉發數據至 Supabase...")
    
    conn.settimeout(RESPONSE_TIMEOUT)

    try:
        consecutive_full_cycle_failures = 0
        while True:
            cycle_had_success = False
            for dev in DEVICES:
                slave_id = dev["id"]
                ch_id = dev["ch"]
                dev_type = dev["type"]
                dev_name = dev["name"]
                
                # 準備寫入資料庫的格式 (欄位對應 database/supabase_schema.sql)
                # _table 只用來路由，寫入前會從 payload 中移除，不是實際欄位
                db_payload = {
                    "channel": ch_id,
                    "updated_at": now_taiwan_str(),
                    "device_name": dev_name,
                    "_table": TEMP_TABLE if dev_type == "IoT-627" else METER_TABLE,
                }

                if dev_type == "IoT-627":
                    all_regs = send_modbus_tcp_request(conn, slave_id, 0x03, 0, 50)

                    if all_regs is None:
                        logging.warning(f"⚠️ {ch_id} ({dev_name}) 無回應 (Timeout)。")
                    else:
                        db_payload["raw_data"] = {f"40{i+1:03d}": val for i, val in enumerate(all_regs)}

                        try:
                            r35 = all_regs[34]
                            r37 = all_regs[36]

                            db_payload.update({
                                "set_temp":            to_signed(all_regs[6]) / 10.0,
                                "control_temp":        to_signed(all_regs[39]) / 10.0,
                                "coil_temp":           to_signed(all_regs[40]) / 10.0,
                                "return_temp":         to_signed(all_regs[41]) / 10.0,
                                "low_pressure":        to_signed(all_regs[42]) / 10.0,
                                "high_pressure":       to_signed(all_regs[44]) / 10.0,
                                "compressor_current":  to_signed(all_regs[46]) / 10.0,
                                "defrost_current":     to_signed(all_regs[48]) / 10.0,
                                "fault_code":          r37,
                                "status_running":          bool((r35 >> 0) & 1),
                                "status_defrost":          bool((r35 >> 1) & 1),
                                "status_drip":             bool((r35 >> 2) & 1),
                                "status_fan_delay":        bool((r35 >> 3) & 1),
                                "status_high_temp_alarm":  bool((r35 >> 4) & 1),
                                "status_low_temp_alarm":   bool((r35 >> 5) & 1),
                                "status_defrost_heater":   bool((r35 >> 6) & 1),
                                "status_fan":              bool((r35 >> 7) & 1),
                                "status_cooling":          bool((r35 >> 8) & 1),
                                "status_low_press_err":    bool((r35 >> 9) & 1),
                                "status_high_press_err":   bool((r35 >> 10) & 1),
                                "status_phase_err":        bool((r35 >> 11) & 1),
                                "status_sensor_err":       bool((r35 >> 12) & 1),
                                "status_overload_err":     bool((r35 >> 13) & 1),
                                "status_door_open":        bool((r35 >> 14) & 1),
                                "status_equip_err":        bool((r35 >> 15) & 1),
                            })
                        except IndexError:
                            pass

                        db_queue.put(db_payload)
                        cycle_had_success = True
                        logging.info(f"📡 {ch_id} ({dev_name}) | 溫度: {db_payload.get('control_temp')} °C | 故障碼: {db_payload.get('fault_code')}")

                elif dev_type == "SPM-3":
                    r1 = send_modbus_tcp_request(conn, slave_id, 0x04, 1030, 70)
                    time.sleep(0.1)
                    r2 = send_modbus_tcp_request(conn, slave_id, 0x04, 1182, 2)

                    if r1 is None or r2 is None:
                        logging.warning(f"⚠️ {ch_id} ({dev_name}) 無回應 (Timeout)。")
                    else:
                        db_payload["raw_data"] = {
                            "1030_1099": list(r1),
                            "1182_1183": list(r2)
                        }

                        def decode_float32(regs, offset):
                            try:
                                raw_bytes = struct.pack('>HH', regs[offset + 1], regs[offset])
                                return round(struct.unpack('>f', raw_bytes)[0], 2)
                            except Exception:
                                return 0.0

                        db_payload.update({
                            "voltage_rs":     decode_float32(r1, 2),
                            "voltage_st":     decode_float32(r1, 4),
                            "voltage_tr":     decode_float32(r1, 6),
                            "voltage_avg":    decode_float32(r1, 8),
                            "frequency":      decode_float32(r1, 20),
                            "current_r":      decode_float32(r1, 22),
                            "current_s":      decode_float32(r1, 24),
                            "current_t":      decode_float32(r1, 26),
                            "current_avg":    decode_float32(r1, 30),
                            "power_total":    decode_float32(r1, 44),
                            "power_factor":   decode_float32(r1, 52),
                            "reactive_power": decode_float32(r1, 66),
                            "apparent_power": decode_float32(r1, 68),
                            "energy_total":   decode_float32(r2, 0),
                        })

                        db_queue.put(db_payload)
                        cycle_had_success = True
                        logging.info(f"⚡ {ch_id} ({dev_name}) | 總電壓: {db_payload.get('voltage_avg')} V | 平均電流: {db_payload.get('current_avg')} A | 用電量: {db_payload.get('energy_total')} kWh")

                time.sleep(POLL_INTERVAL_BETWEEN_DEVICES)

            if cycle_had_success:
                consecutive_full_cycle_failures = 0
            else:
                consecutive_full_cycle_failures += 1
                logging.warning(f"⚠️ 連續 {consecutive_full_cycle_failures} 輪全部設備皆無回應")
                if consecutive_full_cycle_failures >= MAX_FULL_CYCLE_FAILURES:
                    raise ConnectionDeadError(
                        f"連續 {consecutive_full_cycle_failures} 輪全部逾時，判定連線已失效 (可能是靜默斷線)"
                    )

            time.sleep(POLL_INTERVAL_BATCH)

    except (BrokenPipeError, ConnectionResetError, OSError, ConnectionDeadError) as e:
        logging.warning(f"⚠️ W610 連線中斷: {e}")
        logging.info("等待 W610 重新連線...")
    except KeyboardInterrupt:
        raise

def main():
    logging.info("=" * 72)
    logging.info("🚀 啟動 GCP 雲端服務：Modbus TCP 閘道輪詢與 Supabase 寫入")
    logging.info(f"   TCP Server Port: {TCP_SERVER_PORT}")
    logging.info(f"   Supabase Tables: {TEMP_TABLE}, {METER_TABLE}")
    logging.info("=" * 72)

    # 啟動背景 Queue 處理器
    worker_thread = threading.Thread(target=supabase_worker, daemon=True)
    worker_thread.start()

    # 啟動 TCP Server，等待 W610 連入
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', TCP_SERVER_PORT))
    server.listen(1)
    logging.info(f"⏳ TCP Server 已啟動，等待 W610 連入 (Port {TCP_SERVER_PORT})...")

    try:
        while True:
            conn, addr = server.accept()
            try:
                handle_w610_connection(conn, addr)
            except KeyboardInterrupt:
                raise
            finally:
                conn.close()
                logging.info(f"⏳ 等待 W610 重新連入 (Port {TCP_SERVER_PORT})...")
    except KeyboardInterrupt:
        logging.info("\n使用者中斷，停止服務。")
    finally:
        server.close()
        # 通知 worker 停止
        db_queue.put(None)
        worker_thread.join(timeout=2.0)

if __name__ == "__main__":
    main()
