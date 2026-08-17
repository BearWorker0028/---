# -*- coding: utf-8 -*-
"""
裕珍皇 RS485 Modbus RTU 統一點位掃描與 100 筆穩定度測試工具 (IoT627 溫控器 + SPM-3 集合式電錶)

本腳本整合原本分散的掃描程式，為專案中唯一的 RS485 測試工具。

支援設備與功能：
1. IoT627 溫控器 (Holding Registers FC03):
   - Offset 34: 狀態位元 (運轉/除霜/風機/製冷/高壓故障/低壓故障/門開啟/高溫警報)
   - Offset 39: 控制溫度 (control_temp, 0.1 degC)
   - Offset 40: 盤管溫度 (coil_temp, 0.1 degC)
   - Offset 41: 回流管溫 (return_pipe_temp, 0.1 degC)
   - Offset 42: 低壓壓力 (low_pressure, 0.1 bar/psig)
   - Offset 44: 高壓壓力 (high_pressure, 0.1 bar/psig)
   - Offset 46: 壓縮機運轉電流 (compressor_current, 0.1 A)
   - Offset 48: 除霜電熱電流 (defrost_current, 0.1 A)
   - Offset 6:  設定溫度 (control_temp_set, 0.1 degC)
   - Offset 0:  設備起停控制 (equip_start_stop)

2. SPM-3 集合式電錶 (Input Registers FC04):
   - Offset 1032~1036: 三相線電壓 V_rs, V_st, V_tr (Float32, Low-word first)
   - Offset 1052~1056: 三相電流 I_r, I_s, I_t (Float32, Low-word first)
   - Offset 1074: 總有效功率 kW
   - Offset 1082: 功率因數 PF
   - Offset 1182: 累積電量 kWh

常用用法：
  python tools/scan_rs485.py --slaves 1-8 --count 100            # 一樓全設備 (Slave 1~8) 持續讀取 100 筆
  python tools/scan_rs485.py --slaves 11-16 --count 100          # 三樓全設備 (Slave 11~16) 持續讀取 100 筆
  python tools/scan_rs485.py --slaves 1-8 --count 1              # 一樓單次全點位掃描
  python tools/scan_rs485.py --port COM4 --baud 9600             # 自訂 Serial Port 與 Baudrate
"""

import os
import sys
import time
import struct
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

from pymodbus.client import ModbusSerialClient, ModbusTcpClient
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


def scan_iot627(client: ModbusSerialClient, slave_id: int) -> Tuple[bool, Optional[Dict[str, Any]], str, float]:
    """
    讀取並解析 IoT627 溫控器 (Modbus Holding Registers FC03)
    讀取 Offset 34 ~ 50 (共 17 個暫存器) 及 Offset 0, 6
    """
    t0 = time.perf_counter()
    try:
        # 讀取 offset 34 ~ 50 (共 17 個暫存器)
        resp_status = client.read_holding_registers(address=34, count=17, device_id=slave_id)
        if resp_status.isError():
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return False, None, f"Holding Reg 34..50 Read Error: {resp_status}", elapsed_ms

        regs_st = resp_status.registers

        # 讀取 offset 0 & 6
        resp_ctrl = client.read_holding_registers(address=0, count=7, device_id=slave_id)
        start_stop_raw = 0
        set_temp_raw = 0
        if not resp_ctrl.isError():
            start_stop_raw = resp_ctrl.registers[0]
            set_temp_raw = resp_ctrl.registers[6]

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # 位元拆解 Bitfield (Offset 34)
        bitfield = regs_st[0]
        running = bool((bitfield >> 0) & 1)
        defrost = bool((bitfield >> 1) & 1)
        fan = bool((bitfield >> 7) & 1)
        cooling = bool((bitfield >> 8) & 1)
        low_press_err = bool((bitfield >> 9) & 1)
        high_press_err = bool((bitfield >> 10) & 1)
        door_open = bool((bitfield >> 14) & 1)
        stop_status = not running

        # AI 數值計算
        ctrl_temp = round(signed_int16(regs_st[5]) * 0.1, 1)        # offset 39 (40040)
        coil_temp = round(signed_int16(regs_st[6]) * 0.1, 1)        # offset 40 (40041)
        ret_temp = round(signed_int16(regs_st[7]) * 0.1, 1)         # offset 41 (40042)
        low_press = round(signed_int16(regs_st[8]) * 0.1, 1)        # offset 42 (40043)
        high_press = round(regs_st[10] * 0.1, 1)                     # offset 44 (40045)
        comp_curr = round(signed_int16(regs_st[12]) * 0.1, 1)       # offset 46 (40047)
        defrost_curr = round(signed_int16(regs_st[14]) * 0.1, 1)    # offset 48 (40049)
        ctrl_temp_set = round(signed_int16(set_temp_raw) * 0.1, 1)   # offset 6 (40007)
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


def scan_spm3(client: ModbusSerialClient, slave_id: int) -> Tuple[bool, Optional[Dict[str, Any]], str, float]:
    """
    讀取與解析 SPM-3 集合式電錶 (Modbus Input Registers FC04)
    """
    t0 = time.perf_counter()
    try:
        # 讀取 1032 ~ 1083 (共 52 個 Registers)
        resp_main = client.read_input_registers(address=1032, count=52, device_id=slave_id)
        if resp_main.isError():
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return False, None, f"Input Reg 1032..1083 Read Error: {resp_main}", elapsed_ms

        # 讀取 1182 ~ 1183 (累積電量 kWh)
        resp_kwh = client.read_input_registers(address=1182, count=2, device_id=slave_id)
        if resp_kwh.isError():
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return False, None, f"Input Reg 1182 Read Error: {resp_kwh}", elapsed_ms

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        rm = resp_main.registers
        rk = resp_kwh.registers

        v_rs = parse_float32_low_word_first(rm[0], rm[1])      # 1032
        v_st = parse_float32_low_word_first(rm[2], rm[3])      # 1034
        v_tr = parse_float32_low_word_first(rm[4], rm[5])      # 1036
        i_r  = parse_float32_low_word_first(rm[20], rm[21])   # 1052
        i_s  = parse_float32_low_word_first(rm[22], rm[23])   # 1054
        i_t  = parse_float32_low_word_first(rm[24], rm[25])   # 1056
        kw   = parse_float32_low_word_first(rm[42], rm[43])   # 1074
        pf   = parse_float32_low_word_first(rm[50], rm[51])   # 1082
        kwh  = parse_float32_low_word_first(rk[0], rk[1])     # 1182

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


def run_continuous_stability_test(client: ModbusSerialClient, slave_list: List[int], duration: int = 60, interval: float = 1.0, max_count: int = 0):
    """
    連續連線穩定度測試模式 (支援按時間或按指定筆數 max_count 測試)
    """
    import json

    mode_str = f"目標筆數: {max_count} 筆" if max_count > 0 else f"持續時間: {duration} 秒"
    print("\n" + "=" * 80)
    print(f"  RS485 連續連線穩定度與數據測試 ({mode_str}, 輪詢週期: {interval} 秒)")
    print(f"  測試目標 Slave: {slave_list}")
    print("=" * 80 + "\n")

    stats = {sid: {'attempts': 0, 'success': 0, 'fail': 0, 'latencies': [], 'last_val': ''} for sid in slave_list}
    all_readings = []

    start_time = time.time()
    end_time = start_time + duration if max_count == 0 else float('inf')
    cycle_idx = 0

    while True:
        if max_count > 0 and cycle_idx >= max_count:
            break
        if max_count == 0 and time.time() >= end_time:
            break

        cycle_idx += 1
        now_dt = datetime.now()
        now_str = now_dt.strftime('%H:%M:%S')
        elapsed_sec = int(time.time() - start_time)

        progress_info = f"{cycle_idx}/{max_count} 筆" if max_count > 0 else f"{elapsed_sec}/{duration}s"
        print(f"[{now_str}] Cycle #{cycle_idx:03d} ({progress_info}):")

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
                if success:
                    dev_type = 'iot627'

            if not success and (dev_type == 'spm3' or dev_type == 'auto'):
                success, data, msg, elapsed_ms = scan_spm3(client, slave_id)
                if success:
                    dev_type = 'spm3'

            stats[slave_id]['attempts'] += 1

            if success and data:
                stats[slave_id]['success'] += 1
                stats[slave_id]['latencies'].append(elapsed_ms)

                if dev_type == 'iot627':
                    val_summary = f"CtrlTemp={data['control_temperature']:+.1f}°C, Coil={data['coil_temperature']:+.1f}°C, Comp={data['compressor_current']}A, Ret={data['return_pipe_temperature']:+.1f}°C, LowP={data['low_pressure']}bar, HighP={data['high_pressure']}bar"
                else:
                    val_summary = f"Power={data['power_total_kw']}kW, PF={data['power_factor']}, kWh={data['energy_total_kwh']}, V_rs={data['voltage_rs']}V, I_r={data['current_r']}A"

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

            time.sleep(0.02)  # Inter-slave delay

        all_readings.append(cycle_record)

        if interval > 0:
            time.sleep(interval)

    # -- 穩定度統計總表 --
    print("\n" + "=" * 85)
    print(f"  RS485 通訊穩定度測試統計報告 (完成 {cycle_idx} 筆讀取)")
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
            grade = "【優良】通訊極穩定 (100% 穩定)"
        elif rate >= 90.0:
            grade = "【良好】偶有微量丟包"
        elif rate > 0:
            grade = "【警告】丟包率偏高"
        else:
            grade = "【離線】無法連線"

        print(f"Slave #{sid:<2d} | {dname:<22s} | {att:<8d} | {succ:<7d} | {fail:<7d} | {rate:>7.1f}%  | {avg_lat:>6.1f} ms  | {grade}")

    overall_rate = (total_succ_all / total_req_all * 100.0) if total_req_all > 0 else 0.0
    print("=" * 85)
    print(f" 總體統計: 總採樣筆數 {cycle_idx} | 總封包數 {total_req_all} | 成功封包 {total_succ_all} | 平均連線成功率: {overall_rate:.2f}%\n")

    # 保存採樣紀錄至檔案
    os.makedirs('outputs', exist_ok=True)
    output_path = os.path.join('outputs', 'rs485_100_reads_report.json')
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'generated_at': datetime.now().isoformat(),
                'total_cycles': cycle_idx,
                'overall_success_rate': round(overall_rate, 2),
                'slaves': slave_list,
                'stats': stats,
                'readings': all_readings
            }, f, ensure_ascii=False, indent=2)
        print(f"[REPORT] 100 筆詳細採樣資料已成功儲存至: {output_path}\n")
    except Exception as e:
        print(f"[WARN] 儲存採樣報告檔案失敗: {e}")


def main():
    parser = argparse.ArgumentParser(description="裕珍皇 RS485 / Gateway Scan Tool (IoT627 + SPM-3)")
    parser.add_argument('--port', default=os.getenv('RS485_PORT', 'COM4'), help='Serial Port (e.g. COM3, COM4, /dev/ttyUSB0)')
    parser.add_argument('--baud', type=int, default=int(os.getenv('RS485_BAUD', '9600')), help='Baudrate (default 9600)')
    parser.add_argument('--host', default='', help='Gateway IP (如 192.168.1.100，指定此參數切換為 Ethernet Gateway 模式)')
    parser.add_argument('--tcp-port', type=int, default=2000, help='Gateway TCP Port (預設 2000)')
    parser.add_argument('--slaves', default='1-8', help='Slave range, e.g. "1-8" (一樓) 或 "11-16" (三樓)')
    parser.add_argument('--loop', action='store_true', help='開啟每秒持續連線穩定度測試模式')
    parser.add_argument('--count', type=int, default=100, help='指定持續讀取的總筆數 (預設 100 筆)')
    parser.add_argument('--duration', type=int, default=0, help='持續測試時間 (秒)')
    parser.add_argument('--interval', type=float, default=0.5, help='讀取輪詢間隔 (秒)，預設 0.5 秒')
    args = parser.parse_args()

    # 解析 Slave ID 清單
    slave_list = []
    if '-' in args.slaves:
        s_start, s_end = map(int, args.slaves.split('-'))
        slave_list = list(range(s_start, s_end + 1))
    else:
        slave_list = [int(x.strip()) for x in args.slaves.split(',') if x.strip()]

    print("=" * 80)
    print(f"  裕珍皇 RS485 / Ethernet Gateway Modbus 點位掃描工具")
    if args.host:
        print(f"  模式: Ethernet Gateway ({args.host}:{args.tcp_port}) | Slaves: {slave_list} | 採樣筆數: {args.count} 筆")
        client = ModbusTcpClient(
            host=args.host,
            port=args.tcp_port,
            framer=FramerType.RTU,  # Modbus RTU over TCP
            timeout=2
        )
    else:
        print(f"  模式: Direct USB-RS485 ({args.port} @ {args.baud}bps) | Slaves: {slave_list} | 採樣筆數: {args.count} 筆")
        client = ModbusSerialClient(
            port=args.port,
            framer=FramerType.RTU,
            baudrate=args.baud,
            parity='N',
            stopbits=1,
            bytesize=8,
            timeout=1
        )
    print("=" * 80)

    target_desc = f"{args.host}:{args.tcp_port}" if args.host else args.port
    if not client.connect():
        print(f"\n[FAIL] 無法連線至目標裝置 ({target_desc})")
        print("  請檢查：")
        if args.host:
            print(f"  1. 網路線與 Gateway IP ({args.host}) 是否在同一子網段")
            print(f"  2. Gateway TCP Port ({args.tcp_port}) 是否正確且已開啟")
            print("  3. 網關是否工作在 TCP Server / RTU Over TCP 模式")
        else:
            print("  1. USB-to-RS485 轉接線是否妥善插拔")
            print("  2. 裝置管理員中 COM Port 代號是否正確")
            print("  3. 確信沒有其他監控程式正佔用該 Port")
        sys.exit(1)

    print(f"\n[OK] 成功開啟連線至 {target_desc}\n")

    if args.count > 0 or args.loop or args.duration > 0:
        run_continuous_stability_test(client, slave_list, duration=args.duration, interval=args.interval, max_count=args.count)
    else:
        # 單次全區掃描
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

            if success and data:
                print(f"  [v] Slave #{slave_id:02d} [{dev_type.upper()}] {name} ({elapsed_ms:.1f}ms) -> {data}")
            else:
                print(f"  [x] Slave #{slave_id:02d} {name} -> FAIL: {msg}")
            time.sleep(0.05)

    client.close()


if __name__ == '__main__':
    main()
