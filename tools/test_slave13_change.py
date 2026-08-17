# -*- coding: utf-8 -*-
import os
import sys
import time
from pymodbus.client import ModbusSerialClient
from pymodbus.framer import FramerType

SERIAL_PORT = os.getenv('RS485_PORT', 'COM4')
BAUDRATE    = int(os.getenv('RS485_BAUD', '9600'))

def signed_int16(raw):
    return raw - 65536 if raw > 32767 else raw

def parse_bitfield(val):
    bits = [(val >> i) & 1 for i in range(16)]
    return {
        'running': bits[0],
        'defrost': bits[1],
        'drip': bits[2],
        'high_temp_alarm': bits[4],
        'defrost_heater': bits[6],
        'fan': bits[7],
        'cooling': bits[8],
        'low_press_err': bits[9],
        'high_press_err': bits[10],
        'door_open': bits[14],
        'equip_err': bits[15]
    }

def main():
    client = ModbusSerialClient(
        port=SERIAL_PORT,
        framer=FramerType.RTU,
        baudrate=BAUDRATE,
        parity='N',
        stopbits=1,
        bytesize=8,
        timeout=1
    )

    if not client.connect():
        print(f"[FAIL] Cannot open {SERIAL_PORT}")
        return

    print("=" * 70)
    print(f"  Testing Slave #13 (3F 急速庫 20HP) Changes...")
    print("=" * 70)

    # 1. Read Offset 0~15
    resp0 = client.read_holding_registers(address=0, count=16, device_id=13)
    # 2. Read Offset 34~55
    resp34 = client.read_holding_registers(address=34, count=20, device_id=13)

    if not resp0.isError():
        print("\n[Offset 0 ~ 15]:")
        for i, val in enumerate(resp0.registers):
            print(f"  Offset {i:2d} (Modicon {40001+i:5d}): {val} ({signed_int16(val)*0.1:.1f})")

    if not resp34.isError():
        print("\n[Offset 34 ~ 53]:")
        for i, val in enumerate(resp34.registers):
            off = 34 + i
            print(f"  Offset {off:2d} (Modicon {40001+off:5d}): {val} ({signed_int16(val)*0.1:.1f})")

        status_raw = resp34.registers[0]
        status = parse_bitfield(status_raw)
        print("\n[Status Bits - Offset 34 (Modicon 40035)]:")
        print(f"  Raw value: {status_raw}")
        print(f"  - Running  (bit 0): {status['running']}")
        print(f"  - Defrost  (bit 1): {status['defrost']}")
        print(f"  - Fan      (bit 7): {status['fan']}")
        print(f"  - Cooling  (bit 8): {status['cooling']}")
        print(f"  - LowPress (bit 9): {status['low_press_err']}")
        print(f"  - HighPress(bit10): {status['high_press_err']}")

    client.close()

if __name__ == '__main__':
    main()
