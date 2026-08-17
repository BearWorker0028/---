# -*- coding: utf-8 -*-
"""
裕珍皇 Ethernet Gateway Modbus 點位掃描工具 (IoT627 溫控器 + SPM-3 集合式電錶)

專門透過乙太網路網關 (RS485-to-ETH Gateway) 進行 Modbus 點位讀取與通訊測試。

預設網關：192.168.68.200:2000 (對應 1F GW)

使用方法：
  python tools/scan_eth.py                                       # 一樓 1F GW 預設單次掃描 (Slave 1~8)
  python tools/scan_eth.py --count 100                           # 一樓持續讀取 100 筆穩定度測試
  python tools/scan_eth.py --host 192.168.68.200 --slaves 1-8    # 指定 IP 掃描一樓
  python tools/scan_eth.py --host 192.168.x.x --slaves 11-16    # 掃描三樓 3F GW
"""

import os
import sys
import time
import struct
import json
import argparse
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pymodbus.client import ModbusTcpClient
from pymodbus.framer import FramerType

# 已知案場 Slave 與設備名稱對照
KNOWN_DEVICES = {
    1: {'name': '1F 冷凍庫 A (ch01)', 'type': 'iot627'},
    2: {'name': '1F 冷凍庫 B (ch02)', 'type': 'iot627'},
    3: {'name': '1F 冷凍庫 C (ch03)', 'type': 'iot627'},
    4: {'name': '1F 冷凍庫 D (ch04)', 'type': 'iot627'},
    5: {'name': '1F 冷凍庫 E (ch05)', 'type': 'iot627'},
    6: {'name': '1F 緩衝庫 A (ch06)', 'type': 'iot627'},
    7: {'name': '1F 碼頭區 A (ch07)', 'type': 'iot627'},
    8: {'name': '1F 集合式電錶 (ch13)', 'type': 'spm3'},
    11: {'name': '3F 半成品冷凍 A (ch10)', 'type': 'iot627'},
    12: {'name': '3F 半成品冷凍 B (ch11)', 'type': 'iot627'},
    13: {'name': '3F 急速庫 20HP (ch08)', 'type': 'iot627'},
    14: {'name': '3F 急速庫 10HP (ch09)', 'type': 'iot627'},
    15: {'name': '3F 冷藏庫     (ch12)', 'type': 'iot627'},
    16: {'name': '3F 集合式電錶 (ch14)', 'type': 'spm3'},
}


def signed_int16(raw: int) -> int:
    return raw - 65536 if raw > 32767 else raw


def parse_float32_low_word_first(r0: int, r1: int) -> float:
    """IEEE 754 Single Precision Float (Low-word first)"""
    try:
        raw_bytes = struct.pack('>HH', r1, r0)
        return round(struct.unpack('>f', raw_bytes)[0], 2)
    except Exception:
        return 0.0


def scan_iot627(client: ModbusTcpClient, slave_id: int) -> Tuple[bool, Optional[Dict[str, Any]], str, float]:
    """
    透過 Ethernet 讀取並解析 IoT627 溫控器 (Holding Reg Offset 34~50 & 0, 6)
    """
    t0 = time.perf_counter()
    try:
        resp_status = client.read_holding_registers(address=34, count=17, device_id=slave_id)
        if resp_status.isError():
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return False, None, f"Holding Reg Read Error: {resp_status}", elapsed_ms

        regs_st = resp_status.registers

        resp_ctrl = client.read_holding_registers(address=0, count=7, device_id=slave_id)
        start_stop_raw = 0
        set_temp_raw = 0
        if not resp_ctrl.isError():
            start_stop_raw = resp_ctrl.registers[0]
            set_temp_raw = resp_ctrl.registers[6]

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        bitfield = regs_st[0]
        running = bool((bitfield >> 0) & 1)
        defrost = bool((bitfield >> 1) & 1)
        fan = bool((bitfield >> 7) & 1)
        cooling = bool((bitfield >> 8) & 1)
        low_press_err = bool((bitfield >> 9) & 1)
        high_press_err = bool((bitfield >> 10) & 1)
        door_open = bool((bitfield >> 14) & 1)
        stop_status = not running

        ctrl_temp = round(signed_int16(regs_st[5]) * 0.1, 1)
        coil_temp = round(signed_int16(regs_st[6]) * 0.1, 1)
        ret_temp = round(signed_int16(regs_st[7]) * 0.1, 1)
        low_press = round(signed_int16(regs_st[8]) * 0.1, 1)
        high_press = round(regs_st[10] * 0.1, 1)
        comp_curr = round(signed_int16(regs_st[12]) * 0.1, 1)
        defrost_curr = round(signed_int16(regs_st[14]) * 0.1, 1)
        ctrl_temp_set = round(signed_int16(set_temp_raw) * 0.1, 1)
        equip_start_stop = bool(start_stop_raw & 1)

        result = {
            'control_temperature': ctrl_temp,
            'coil_temperature': coil_temp,
            'return_pipe_temperature': ret_temp,
            'compressor_current': comp_curr,
            'defrost_current': defrost_curr,
            'high_pressure': high_press,
            'low_pressure': low_press,
            'control_temperature_set': ctrl_temp_set,
            'equipment_start_stop': equip_start_stop,
            'running_status': running,
            'cooling_status': cooling,
            'defrost_status': defrost,
            'stop_status': stop_status,
            'fan_status': fan,
            'door_open': door_open,
            'low_press_err': low_press_err,
            'high_press_err': high_press_err,
            'status_bitfield_raw': bitfield
        }

        return True, result, "OK", elapsed_ms

    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return False, None, str(e), elapsed_ms


def scan_spm3(client: ModbusTcpClient, slave_id: int) -> Tuple[bool, Optional[Dict[str, Any]], str, float]:
    """
    透過 Ethernet 讀取並解析 SPM-3 集合式電錶 (Input Reg Offset 1032~1083 & 1182)
    """
    t0 = time.perf_counter()
    try:
        resp_main = client.read_input_registers(address=1032, count=52, device_id=slave_id)
        if resp_main.isError():
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return False, None, f"Input Reg 1032 Read Error: {resp_main}", elapsed_ms

        resp_kwh = client.read_input_registers(address=1182, count=2, device_id=slave_id)
        if resp_kwh.isError():
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return False, None, f"Input Reg 1182 Read Error: {resp_kwh}", elapsed_ms

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        rm = resp_main.registers
        rk = resp_kwh.registers

        v_rs = parse_float32_low_word_first(rm[0], rm[1])
        v_st = parse_float32_low_word_first(rm[2], rm[3])
        v_tr = parse_float32_low_word_first(rm[4], rm[5])
        i_r  = parse_float32_low_word_first(rm[20], rm[21])
        i_s  = parse_float32_low_word_first(rm[22], rm[23])
        i_t  = parse_float32_low_word_first(rm[24], rm[25])
        kw   = parse_float32_low_word_first(rm[42], rm[43])
        pf   = parse_float32_low_word_first(rm[50], rm[51])
        kwh  = parse_float32_low_word_first(rk[0], rk[1])

        result = {
            'voltage_rs': v_rs,
            'voltage_st': v_st,
            'voltage_tr': v_tr,
            'current_r': i_r,
            'current_s': i_s,
            'current_t': i_t,
            'power_total_kw': kw,
            'power_factor': pf,
            'energy_total_kwh': kwh
        }
        return True, result, "OK", elapsed_ms

    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return False, None, str(e), elapsed_ms


def run_eth_scan(client: ModbusTcpClient, slave_list: List[int], max_count: int = 1, interval: float = 0.5, host: str = ''):
    """
    執行 Ethernet 網關讀取與穩定度測試
    """
    print("\n" + "=" * 85)
    print(f"  Ethernet Gateway RS485 Modbus 點位掃描 (Target Gateway: {host})")
    print(f"  測試目標 Slave: {slave_list} | 目標筆數: {max_count} 筆 | 輪詢週期: {interval}s")
    print("=" * 85 + "\n")

    stats = {sid: {'attempts': 0, 'success': 0, 'fail': 0, 'latencies': [], 'last_val': ''} for sid in slave_list}
    all_readings = []

    start_time = time.time()
    cycle_idx = 0

    while cycle_idx < max_count:
        cycle_idx += 1
        now_dt = datetime.now()
        now_str = now_dt.strftime('%H:%M:%S')

        print(f"[{now_str}] ETH Cycle #{cycle_idx:03d} ({cycle_idx}/{max_count}):")

        cycle_record = {
            'cycle': cycle_idx,
            'timestamp': now_dt.isoformat(),
            'devices': {}
        }

        for slave_id in slave_list:
            dev_info = KNOWN_DEVICES.get(slave_id, {'name': f'Slave #{slave_id}', 'type': 'auto'})
            name = dev_info['name']
            dev_type = dev_info['type']

            success, data, msg, elapsed_ms = False, None, "", 0.0

            if dev_type == 'iot627' or dev_type == 'auto':
                success, data, msg, elapsed_ms = scan_iot627(client, slave_id)
                if success: dev_type = 'iot627'

            if not success and (dev_type == 'spm3' or dev_type == 'auto'):
                success, data, msg, elapsed_ms = scan_spm3(client, slave_id)
                if success: dev_type = 'spm3'

            stats[slave_id]['attempts'] += 1

            if success and data:
                stats[slave_id]['success'] += 1
                stats[slave_id]['latencies'].append(elapsed_ms)

                if dev_type == 'iot627':
                    val_summary = f"CtrlTemp={data['control_temperature']:+.1f}°C, Coil={data['coil_temperature']:+.1f}°C, Comp={data['compressor_current']}A, LowP={data['low_pressure']}bar, HighP={data['high_pressure']}bar"
                else:
                    val_summary = f"Power={data['power_total_kw']}kW, PF={data['power_factor']}, kWh={data['energy_total_kwh']}, V_rs={data['voltage_rs']}V"

                stats[slave_id]['last_val'] = val_summary
                succ_rate = (stats[slave_id]['success'] / stats[slave_id]['attempts']) * 100.0
                print(f"  [v] Slave #{slave_id:02d} [{name:<22s}] ({elapsed_ms:5.1f}ms) -> {val_summary} (成功率: {succ_rate:.1f}%)")

                cycle_record['devices'][str(slave_id)] = {
                    'name': name,
                    'type': dev_type,
                    'status': 'OK',
                    'latency_ms': round(elapsed_ms, 1),
                    'data': data
                }
            else:
                stats[slave_id]['fail'] += 1
                succ_rate = (stats[slave_id]['success'] / stats[slave_id]['attempts']) * 100.0
                print(f"  [x] Slave #{slave_id:02d} [{name:<22s}] FAIL ({msg}) (成功率: {succ_rate:.1f}%)")
                cycle_record['devices'][str(slave_id)] = {
                    'name': name,
                    'type': dev_type,
                    'status': 'FAIL',
                    'error': msg
                }

            time.sleep(0.02)

        all_readings.append(cycle_record)

        if cycle_idx < max_count and interval > 0:
            time.sleep(interval)

    # 報表輸出
    print("\n" + "=" * 85)
    print(f"  Ethernet Gateway 通訊品質統計報告 (完成 {cycle_idx} 筆讀取)")
    print("=" * 85)
    print(f"{'Slave ID':<9s} | {'設備名稱':<24s} | {'總請求':<6s} | {'成功':<5s} | {'失敗':<5s} | {'成功率 %':<8s} | {'平均延遲':<9s} | {'品質評估'}")
    print("-" * 85)

    total_req_all = 0
    total_succ_all = 0

    for sid in slave_list:
        dname = KNOWN_DEVICES.get(sid, {}).get('name', f'Slave #{sid}')
        st = stats[sid]
        att = st['attempts']
        succ = st['success']
        fail = st['fail']
        rate = (succ / att * 100.0) if att > 0 else 0.0
        avg_lat = (sum(st['latencies']) / len(st['latencies'])) if st['latencies'] else 0.0

        total_req_all += att
        total_succ_all += succ

        if rate >= 98.0:
            grade = "【優良】乙太網路極穩定 (100% 成功)"
        elif rate >= 90.0:
            grade = "【良好】偶有連線延遲"
        elif rate > 0:
            grade = "【警告】連線丟包偏高"
        else:
            grade = "【離線】無法連線"

        print(f"Slave #{sid:<2d} | {dname:<22s} | {att:<8d} | {succ:<7d} | {fail:<7d} | {rate:>7.1f}%  | {avg_lat:>6.1f} ms  | {grade}")

    overall_rate = (total_succ_all / total_req_all * 100.0) if total_req_all > 0 else 0.0
    print("=" * 85)
    print(f" 總體統計: Gateway={host} | 總採樣筆數 {cycle_idx} | 總封包數 {total_req_all} | 成功封包 {total_succ_all} | 平均連線成功率: {overall_rate:.2f}%\n")

    os.makedirs('outputs', exist_ok=True)
    output_path = os.path.join('outputs', 'scan_eth_report.json')
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'generated_at': datetime.now().isoformat(),
                'gateway_host': host,
                'total_cycles': cycle_idx,
                'overall_success_rate': round(overall_rate, 2),
                'slaves': slave_list,
                'stats': stats,
                'readings': all_readings
            }, f, ensure_ascii=False, indent=2)
        print(f"[REPORT] ETH 詳細採樣報告已儲存至: {output_path}\n")
    except Exception as e:
        print(f"[WARN] 儲存採樣報告檔案失敗: {e}")


def main():
    default_host = os.getenv('MODBUS_HOST', '192.168.68.200')
    default_port = int(os.getenv('MODBUS_PORT', '2000'))

    parser = argparse.ArgumentParser(description="裕珍皇 Ethernet Gateway Modbus Scan Tool")
    parser.add_argument('--host', default=default_host, help=f'Gateway IP 位址 (預設 {default_host})')
    parser.add_argument('--port', type=int, default=default_port, help=f'Gateway TCP Port (預設 {default_port})')
    parser.add_argument('--slaves', default='1-8', help='Slave 範圍，例如 "1-8" (1F GW) 或 "11-16" (3F GW)')
    parser.add_argument('--count', type=int, default=1, help='指定持續讀取的採樣筆數 (預設 1 筆，填 100 為穩定度測試)')
    parser.add_argument('--interval', type=float, default=0.5, help='讀取輪詢間隔 (秒)，預設 0.5 秒')
    args = parser.parse_args()

    slave_list = []
    if '-' in args.slaves:
        s_start, s_end = map(int, args.slaves.split('-'))
        slave_list = list(range(s_start, s_end + 1))
    else:
        slave_list = [int(x.strip()) for x in args.slaves.split(',') if x.strip()]

    print("=" * 85)
    print(f"  裕珍皇 Ethernet Modbus Gateway 專用點位掃描工具 (scan_eth)")
    print(f"  Target Gateway: {args.host}:{args.port} | Slaves: {slave_list} | 採樣筆數: {args.count}")
    print("=" * 85)

    client = ModbusTcpClient(
        host=args.host,
        port=args.port,
        framer=FramerType.RTU,
        timeout=2.0
    )

    if not client.connect():
        print(f"\n[FAIL] 無法連線至 Ethernet Gateway ({args.host}:{args.port})")
        print("  請檢查：")
        print(f"  1. 電腦或 Wi-Fi 是否已連至網關同一網段 (如 {args.host})")
        print(f"  2. 網關 Port ({args.port}) 是否為 TCP Server 模式")
        sys.exit(1)

    print(f"\n[OK] 成功建立 Ethernet Gateway 連線 ({args.host}:{args.port})\n")

    run_eth_scan(client, slave_list, max_count=args.count, interval=args.interval, host=args.host)

    client.close()


if __name__ == '__main__':
    main()
