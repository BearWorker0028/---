# -*- coding: utf-8 -*-
"""
GCP 雲端專用：W610 Modbus TCP 閘道輪詢服務 (TCP Server 模式)
- 部署於 GCP 雲端伺服器 (Cloud VM) 執行
- GCP 開啟 TCP Server，等待案場 W610 (TCP Client) 主動連入
- W610 設定為 "Modbus TCP <=> Modbus RTU" 閘道模式
- GCP 透過 Modbus TCP 格式輪詢 IoT-627 (溫控) 與 SPM-3 (電錶)
- 將 JSON 即時數據發布至 GCP 雲端 MQTT Broker (iot627/realtime/<ch>)
"""

import sys
import time
import json
import io
import struct
import socket
import threading
import paho.mqtt.client as mqtt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# ── 1. 系統與通訊設定 ──
TCP_SERVER_PORT = 8801              # GCP 開放的 TCP Server Port (W610 會連到這裡)
MQTT_BROKER = '127.0.0.1'          # GCP 本機 Mosquitto 服務
MQTT_PORT = 1883                   # MQTT 埠號
DOCKER_TOPIC_PREFIX = 'iot627/realtime'

POLL_INTERVAL_BETWEEN_DEVICES = 0.3  # 每次讀取不同設備之間的延遲 (秒)
POLL_INTERVAL_BATCH = 3.0            # 每輪掃描完畢後的延遲 (秒)
RESPONSE_TIMEOUT = 3.0               # 等待 W610 回傳的 Timeout 時間 (秒)

DEVICES = [
    {"ch": "ch01", "id": 1, "type": "IoT-627", "name": "1F 冷凍庫 A"},
    {"ch": "ch02", "id": 2, "type": "IoT-627", "name": "1F 冷凍庫 B"},
    {"ch": "ch03", "id": 3, "type": "IoT-627", "name": "1F 冷凍庫 C"},
    {"ch": "ch04", "id": 4, "type": "IoT-627", "name": "1F 冷凍庫 D"},
    {"ch": "ch05", "id": 5, "type": "IoT-627", "name": "1F 冷凍庫 E"},
    {"ch": "ch06", "id": 6, "type": "IoT-627", "name": "1F 緩衝庫 A"},
    {"ch": "ch07", "id": 7, "type": "IoT-627", "name": "1F 碼頭區 A"},
    {"ch": "ch13", "id": 8, "type": "SPM-3",   "name": "1F 集合式電錶"},
]

# ── 2. Modbus TCP 通訊函式 ──
trans_id_counter = 0

def next_trans_id():
    """產生遞增的 Transaction ID"""
    global trans_id_counter
    trans_id_counter = (trans_id_counter + 1) % 65536
    return trans_id_counter

def send_modbus_tcp_request(conn, slave_id, function_code, start_addr, reg_count):
    """
    發送 Modbus TCP 請求並等待回應
    回傳: tuple of registers (成功) 或 None (失敗)
    """
    tid = next_trans_id()
    
    # 建立 Modbus TCP 封包 (MBAP Header + PDU，不需要 CRC)
    pdu = struct.pack('>BBHH', slave_id, function_code, start_addr, reg_count)
    mbap = struct.pack('>HHH', tid, 0x0000, len(pdu))
    request = mbap + pdu
    
    try:
        conn.sendall(request)
    except (BrokenPipeError, ConnectionResetError, OSError):
        return None
    
    # 接收回應
    try:
        # 先讀取 MBAP Header (6 bytes)
        header = b''
        while len(header) < 6:
            chunk = conn.recv(6 - len(header))
            if not chunk:
                return None
            header += chunk
        
        resp_tid, resp_proto, resp_len = struct.unpack('>HHH', header)
        
        # 再讀取剩餘的資料 (resp_len bytes)
        body = b''
        while len(body) < resp_len:
            chunk = conn.recv(resp_len - len(body))
            if not chunk:
                return None
            body += chunk
        
        resp_unit_id = body[0]
        resp_fc = body[1]
        
        # 檢查是否為錯誤回應
        if resp_fc >= 0x80:
            error_code = body[2]
            print(f"  ⚠️ Slave {resp_unit_id} 回傳 Modbus 錯誤碼: {error_code}")
            return None
        
        # 正常回應: Unit ID(1) + FC(1) + ByteCount(1) + Data(N)
        byte_count = body[2]
        data = body[3:3+byte_count]
        
        reg_count_actual = byte_count // 2
        regs = struct.unpack(f'>{reg_count_actual}H', data)
        return regs
        
    except socket.timeout:
        return None
    except Exception as e:
        print(f"  ❌ 接收回應時發生錯誤: {e}")
        return None

# ── 3. 資料解碼函式 ──
def to_signed(raw):
    """將無號 16-bit 轉成有號整數 (處理負溫度與負壓)"""
    return raw - 65536 if raw > 32767 else raw

def decode_float32(regs, offset):
    """解碼 SPM-3 的 Float32 (2 Words, Low-word First / CDAB)"""
    try:
        raw_bytes = struct.pack('>HH', regs[offset+1], regs[offset])
        return round(struct.unpack('>f', raw_bytes)[0], 2)
    except Exception:
        return 0.0

# ── 4. MQTT 連線 ──
def init_mqtt():
    """初始化 MQTT 連線 (用於發布 JSON 即時數據)"""
    try:
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        mqtt_client = mqtt.Client()
    
    def on_connect(client, userdata, flags, *args):
        print("✅ 成功連線至本機 MQTT Broker！")
    
    mqtt_client.on_connect = on_connect
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
    return mqtt_client

# ── 5. 主程式 ──
def handle_w610_connection(conn, addr, mqtt_client):
    """處理一個 W610 的連線：持續輪詢設備並發布 JSON"""
    print(f"\n🔗 W610 已連入！來源: {addr[0]}:{addr[1]}")
    print("開始自動輪詢並轉發數據...\n")
    
    conn.settimeout(RESPONSE_TIMEOUT)
    
    try:
        while True:
            for dev in DEVICES:
                slave_id = dev["id"]
                ch_id = dev["ch"]
                dev_type = dev["type"]
                dev_name = dev["name"]
                
                payload_json = {
                    "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "channel": ch_id,
                    "slave_id": slave_id,
                    "device_type": dev_type,
                    "device_name": dev_name,
                    "raw": {},
                    "parsed": {}
                }

                if dev_type == "IoT-627":
                    # IoT-627: FC03, 起始位址 0, 讀取 50 個暫存器
                    all_regs = send_modbus_tcp_request(conn, slave_id, 0x03, 0, 50)
                    
                    if all_regs is None:
                        print(f"[{payload_json['timestamp']}] ⚠️ {ch_id} ({dev_name}) 無回應 (Timeout)。")
                    else:
                        payload_json["raw"] = {f"40{i+1:03d}": val for i, val in enumerate(all_regs)}
                        
                        try:
                            r35 = all_regs[34]  # 40035
                            r37 = all_regs[36]  # 40037
                            
                            payload_json["parsed"] = {
                                "set_control_temp":   to_signed(all_regs[6]) / 10.0,
                                "control_temp":       to_signed(all_regs[39]) / 10.0,
                                "coil_temp":          to_signed(all_regs[40]) / 10.0,
                                "return_temp":        to_signed(all_regs[41]) / 10.0,
                                "low_pressure":       to_signed(all_regs[42]) / 10.0,
                                "high_pressure":      to_signed(all_regs[44]) / 10.0,
                                "compressor_current": to_signed(all_regs[46]) / 10.0,
                                "fault_code":         r37,
                                "status_run":       (r35 >> 0) & 1,
                                "status_defrost":   (r35 >> 1) & 1,
                                "status_alarm":     (r35 >> 4) & 1,
                                "status_fan":       (r35 >> 7) & 1,
                                "status_cool":      (r35 >> 8) & 1,
                                "status_door":      (r35 >> 14) & 1,
                            }
                        except IndexError:
                            pass
                        
                        topic = f"{DOCKER_TOPIC_PREFIX}/{ch_id}"
                        mqtt_client.publish(topic, json.dumps(payload_json, ensure_ascii=False))
                            
                        print(f"[{payload_json['timestamp']}] 📡 {ch_id} ({dev_name}) | "
                              f"溫度: {payload_json['parsed'].get('control_temp')} °C | "
                              f"故障碼: {payload_json['parsed'].get('fault_code')}")

                elif dev_type == "SPM-3":
                    # SPM-3 第一段: FC04, 起始位址 1030, 讀取 70 個暫存器
                    r1 = send_modbus_tcp_request(conn, slave_id, 0x04, 1030, 70)
                    
                    time.sleep(0.1)  # 兩次請求間隔
                    
                    # SPM-3 第二段: FC04, 起始位址 1182, 讀取 2 個暫存器
                    r2 = send_modbus_tcp_request(conn, slave_id, 0x04, 1182, 2)
                        
                    if r1 is None or r2 is None:
                        print(f"[{payload_json['timestamp']}] ⚠️ {ch_id} ({dev_name}) 無回應 (Timeout)。")
                    else:
                        payload_json["raw"] = {
                            "1030_1099": list(r1),
                            "1182_1183": list(r2)
                        }
                        
                        payload_json["parsed"] = {
                            "voltage_a":      decode_float32(r1, 0),    # 1030
                            "voltage_rs":     decode_float32(r1, 2),    # 1032
                            "voltage_st":     decode_float32(r1, 4),    # 1034
                            "voltage_tr":     decode_float32(r1, 6),    # 1036
                            "voltage_ll_avg": decode_float32(r1, 8),    # 1038
                            "frequency":      decode_float32(r1, 20),   # 1050
                            "current_r":      decode_float32(r1, 22),   # 1052
                            "current_s":      decode_float32(r1, 24),   # 1054
                            "current_t":      decode_float32(r1, 26),   # 1056
                            "current_avg":    decode_float32(r1, 30),   # 1060
                            "current_sum":    decode_float32(r1, 36),   # 1066
                            "power_total":    decode_float32(r1, 44),   # 1074
                            "power_factor":   decode_float32(r1, 52),   # 1082
                            "reactive_power": decode_float32(r1, 66),   # 1096
                            "apparent_power": decode_float32(r1, 68),   # 1098
                            "energy_total":   decode_float32(r2, 0),    # 1182
                        }
                        
                        topic = f"{DOCKER_TOPIC_PREFIX}/{ch_id}"
                        mqtt_client.publish(topic, json.dumps(payload_json, ensure_ascii=False))
                            
                        print(f"[{payload_json['timestamp']}] ⚡ {ch_id} ({dev_name}) | "
                              f"總電壓: {payload_json['parsed'].get('voltage_ll_avg')} V | "
                              f"總電流: {payload_json['parsed'].get('current_sum')} A | "
                              f"用電量: {payload_json['parsed'].get('energy_total')} kWh")
                              
                time.sleep(POLL_INTERVAL_BETWEEN_DEVICES)

            time.sleep(POLL_INTERVAL_BATCH)
            
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        print(f"\n⚠️ W610 連線中斷: {e}")
        print("等待 W610 重新連線...\n")
    except KeyboardInterrupt:
        raise

def main():
    print("=" * 72)
    print("🚀 啟動 GCP 雲端服務：Modbus TCP 閘道輪詢與轉發")
    print(f"   TCP Server Port: {TCP_SERVER_PORT}")
    print(f"   MQTT Broker:     {MQTT_BROKER}:{MQTT_PORT}")
    print("=" * 72)

    # 初始化 MQTT
    mqtt_client = init_mqtt()
    time.sleep(1)

    # 啟動 TCP Server，等待 W610 連入
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', TCP_SERVER_PORT))
    server.listen(1)
    print(f"\n⏳ TCP Server 已啟動，等待 W610 連入 (Port {TCP_SERVER_PORT})...")

    try:
        while True:
            conn, addr = server.accept()
            try:
                handle_w610_connection(conn, addr, mqtt_client)
            except KeyboardInterrupt:
                raise
            finally:
                conn.close()
                print(f"⏳ 等待 W610 重新連入 (Port {TCP_SERVER_PORT})...")
    except KeyboardInterrupt:
        print("\n使用者中斷，停止服務。")
    finally:
        server.close()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

if __name__ == "__main__":
    main()
