# -*- coding: utf-8 -*-
"""
裕珍皇 3F 電盤 Gateway (GW2) 獨立連線與診斷測試工具

專門針對 3F 配電盤 Gateway (GW2: 192.168.1.101) 進行連線診斷、網路封包延遲、
Web 管理介面狀態抓取以及 Modbus 轉發埠 (Port 5001) 連線穩定度測試。

使用方法：
  python tools/scan_gw2.py                                     # GW2 預設連線與診斷測試
  python tools/scan_gw2.py --count 50                          # 持續進行 50 次連線穩定度與延遲測試
  python tools/scan_gw2.py --host 192.168.1.101 --port 5001  # 自訂 IP 與 Port
"""

import os
import sys
import time
import socket
import json
import argparse
import urllib.request
import urllib.parse
import base64
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from pymodbus.client import ModbusTcpClient
    from pymodbus.framer import FramerType
    HAS_PYMODBUS = True
except ImportError:
    HAS_PYMODBUS = False


GW2_3F_SLAVES = {
    11: {'name': '3F 半成品冷凍 A (ch10)', 'type': 'iot627', 'unit': '°C'},
    12: {'name': '3F 半成品冷凍 B (ch11)', 'type': 'iot627', 'unit': '°C'},
    13: {'name': '3F 急速庫 20HP (ch08)', 'type': 'iot627', 'unit': '°C'},
    14: {'name': '3F 急速庫 10HP (ch09)', 'type': 'iot627', 'unit': '°C'},
    15: {'name': '3F 冷藏庫     (ch12)', 'type': 'iot627', 'unit': '°C'},
    16: {'name': '3F 集合式電錶 (ch14)', 'type': 'spm3',   'unit': 'kWh'},
}


def test_tcp_port(host: str, port: int, timeout: float = 1.0) -> Tuple[bool, float, str]:
    """測試特定 TCP Port 之連線與延遲 (ms)"""
    t0 = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        res = s.connect_ex((host, port))
        latency = (time.perf_counter() - t0) * 1000.0
        s.close()
        if res == 0:
            return True, latency, "CONNECTED"
        else:
            return False, latency, f"Error Code {res}"
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000.0
        return False, latency, str(e)


def fetch_gw2_web_info(host: str, web_port: int = 80) -> Tuple[bool, Dict[str, Any], str]:
    """讀取 GW2 Web 管理介面參數與 MAC 位址"""
    url = f"http://{host}:{web_port}/"
    auth = base64.b64encode('admin:123456'.encode()).decode()
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Basic {auth}')
    
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            
            # 解析 MAC 位址
            mac = "未知"
            if "MAC:" in content:
                try:
                    mac = content.split("MAC:")[1].split("</p>")[0].strip()
                except Exception:
                    pass
            
            # 解析工作模式
            workmode = "未知"
            if "Modbus TCP/IP" in content:
                workmode = "Modbus TCP/IP 服務端"
            elif "TCP服务端" in content:
                workmode = "TCP 服務端"
            
            return True, {
                'mac': mac,
                'workmode': workmode,
                'http_status': resp.status,
                'raw_len': len(content)
            }, "OK"
    except Exception as e:
        return False, {}, str(e)


def run_gw2_scan(host: str = "192.168.1.101", port: int = 5001, web_port: int = 80, count: int = 1):
    print("=" * 85)
    print(f"  裕珍皇 3F 電盤 Gateway (GW2) 獨立連線與診斷測試工具")
    print(f"  目標網關 IP: {host} | 通訊 Port: {port} | Web Port: {web_port} | 測試輪數: {count}")
    print("=" * 85)

    # 1. 網絡層與 Web Port 診斷
    print("\n【階段 1：GW2 網路層與 Web 管理服務診斷】")
    web_ok, latency_web, err_web = test_tcp_port(host, web_port)
    if web_ok:
        print(f"  [SUCCESS] Web 管理介面 (Port {web_port}): 正常連通 (延遲: {latency_web:.1f} ms)")
        info_ok, info_dict, info_err = fetch_gw2_web_info(host, web_port)
        if info_ok:
            print(f"    - GW2 MAC 位址: {info_dict.get('mac')}")
            print(f"    - 工作模式設定: {info_dict.get('workmode')}")
    else:
        print(f"  [FAIL] Web 管理介面 (Port {web_port}): 無法連線 ({err_web})")

    # 2. Modbus 數據轉發 Port 診斷
    print("\n【階段 2：GW2 Modbus 數據轉發埠 (Port {0}) 診斷】".format(port))
    data_ok, latency_data, err_data = test_tcp_port(host, port)
    if data_ok:
        print(f"  [SUCCESS] Modbus 數據埠 (Port {port}): TCP 握手成功 (延遲: {latency_data:.1f} ms)")
    else:
        print(f"  [FAIL] Modbus 數據埠 (Port {port}): 連線失敗 ({err_data})")
        print("  請確認 GW2 已啟動數據轉發功能。")
        return

    # 3. 連線穩定度輪詢測試 (如 count > 1)
    stats = {
        'attempts': 0,
        'success': 0,
        'fail': 0,
        'latencies': []
    }

    print(f"\n【階段 3：GW2 Socket 持續連線穩定度測試 (共 {count} 筆)】")
    for i in range(1, count + 1):
        ok, lat, err = test_tcp_port(host, port)
        stats['attempts'] += 1
        if ok:
            stats['success'] += 1
            stats['latencies'].append(lat)
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] 連線 Cycle #{i:03d}/{count}: 成功 (延遲 {lat:.1f} ms)")
        else:
            stats['fail'] += 1
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] 連線 Cycle #{i:03d}/{count}: 失敗 ({err})")
        
        if count > 1 and i < count:
            time.sleep(0.3)

    avg_lat = (sum(stats['latencies']) / len(stats['latencies'])) if stats['latencies'] else 0.0
    succ_rate = (stats['success'] / stats['attempts']) * 100.0 if stats['attempts'] > 0 else 0.0

    # 4. Modbus RS485 設備連線測試 (現場預備)
    print("\n【階段 4：GW2 下掛 3F RS485 Modbus 點位測試 (Slave 11~16)】")
    print("  [提示] 若目前為台架/非案場環境，下掛 RS485 實體設備未接線屬正常現象。")

    slave_results = {}
    if HAS_PYMODBUS:
        client = ModbusTcpClient(host, port=port, framer=FramerType.RTU, timeout=0.8)
        if client.connect():
            for sid, dev in GW2_3F_SLAVES.items():
                t0 = time.perf_counter()
                try:
                    if dev['type'] == 'iot627':
                        resp = client.read_holding_registers(address=39, count=1, device_id=sid)
                    else:
                        resp = client.read_input_registers(address=1182, count=2, device_id=sid)
                    
                    ms = (time.perf_counter() - t0) * 1000.0
                    if not resp.isError():
                        print(f"  [ONLINE] Slave #{sid:02d} ({dev['name']}): 讀取成功 (延遲: {ms:.1f} ms)")
                        slave_results[sid] = {'status': 'ONLINE', 'latency_ms': round(ms, 1)}
                    else:
                        print(f"  [OFFLINE] Slave #{sid:02d} ({dev['name']}): 未回應 (未在案場/未接線)")
                        slave_results[sid] = {'status': 'OFFLINE', 'note': 'No response from RS485 device'}
                except Exception as ex:
                    slave_results[sid] = {'status': 'ERROR', 'error': str(ex)}
            client.close()
    else:
        print("  [SKIP] 未安裝 pymodbus，跳過 RS485 點位測試。")

    # 5. 總結報告
    print("\n" + "=" * 85)
    print("  GW2 3F 電盤網關 連線測試與品質統計報告")
    print("=" * 85)
    print(f"  - 網關 IP: {host} (Port {port})")
    print(f"  - TCP 總測試次數: {stats['attempts']}")
    print(f"  - TCP 成功次數: {stats['success']} | 失敗次數: {stats['fail']}")
    print(f"  - 網關連線成功率: {succ_rate:.2f}%")
    print(f"  - 平均 TCP 回應延遲: {avg_lat:.1f} ms")
    
    if succ_rate >= 99.0:
        print("  - 品質評估: 【優良】GW2 網關網路與 TCP 轉發極度穩定")
    elif succ_rate >= 90.0:
        print("  - 品質評估: 【尚可】有少量丟包")
    else:
        print("  - 品質評估: 【不佳】網路連線不穩定")

    # 儲存報告
    report_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs')
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, 'scan_gw2_report.json')

    report_data = {
        'generated_at': datetime.now().isoformat(),
        'target_host': host,
        'target_port': port,
        'web_port': web_port,
        'stats': {
            'attempts': stats['attempts'],
            'success': stats['success'],
            'fail': stats['fail'],
            'success_rate_percent': round(succ_rate, 2),
            'avg_latency_ms': round(avg_lat, 2)
        },
        'slave_results': slave_results
    }

    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"\n[REPORT] 詳細診斷報告已儲存至: {report_path}")
    except Exception as e:
        print(f"儲存報告失敗: {e}")


def main():
    parser = argparse.ArgumentParser(description="裕珍皇 GW2 3F 電盤網關 獨立連線與診斷測試工具")
    parser.add_argument("--host", default="192.168.1.101", help="GW2 網關 IP (預設: 192.168.1.101)")
    parser.add_argument("--port", type=int, default=5001, help="GW2 Modbus 數據轉發 Port (預設: 5001)")
    parser.add_argument("--web-port", type=int, default=80, help="GW2 Web 管理介面 Port (預設: 80)")
    parser.add_argument("--count", type=int, default=1, help="測試輪數 (預設: 1)")

    args = parser.parse_args()
    run_gw2_scan(host=args.host, port=args.port, web_port=args.web_port, count=args.count)


if __name__ == '__main__':
    main()
