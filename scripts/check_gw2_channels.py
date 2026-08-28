# -*- coding: utf-8 -*-
import sys
import requests

sys.stdout.reconfigure(encoding='utf-8')

r = requests.get('http://127.0.0.1:88/api/temperatures')
data = r.json()

print('=== GW2 現場設備 (ch08 ~ ch12, ch14) 狀態檢驗 ===')
for ch in ['ch08', 'ch09', 'ch10', 'ch11', 'ch12']:
    d = data.get(ch, {})
    name = d.get('name')
    t_ctrl = d.get('control_temperature')
    t_coil = d.get('coil_temperature')
    c_comp = d.get('compressor_current')
    p_hi = d.get('high_pressure')
    p_lo = d.get('low_pressure')
    t_set = d.get('control_temperature_set')
    st = d.get('status')
    st_run = d.get('running_status')
    st_cool = d.get('cooling_status')
    st_def = d.get('defrost_status')
    ts = d.get('timestamp')
    print(f"[{ch}] {name}: 控溫={t_ctrl}°C, 盤管={t_coil}°C, 電流={c_comp}A, 高壓={p_hi}bar, 低壓={p_lo}bar, 設定={t_set}°C | 運轉={st_run}, 製冷={st_cool}, 除霜={st_def} | 狀態={st} | 更新={ts}")

d14 = data.get('ch14', {})
p = d14.get('power', {})
print(f"\n[ch14] {d14.get('name')}: 電壓={p.get('voltage_ll_avg')}V (RS={p.get('voltage_rs')}, ST={p.get('voltage_st')}, TR={p.get('voltage_tr')}) | 電流={p.get('current_avg')}A (R={p.get('current_r')}, S={p.get('current_s')}, T={p.get('current_t')}) | 功率={p.get('kw')}kW | 累計={p.get('kwh')}kWh | PF={p.get('power_factor')} | 頻率={p.get('frequency')}Hz | 更新={d14.get('timestamp')}")
