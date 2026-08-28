# -*- coding: utf-8 -*-
import sys
import json
import requests

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_URL = 'http://127.0.0.1:88'

print('====================================================')
print('  測試 1: /api/power_chart_data 趨勢圖 API 驗證')
print('====================================================')

test_configs = [
    {'name': '3F 電錶 (ch14) - 用電量柱狀 (6h)', 'params': {'ch': 'ch14', 'field': 'daily_kwh', 'range': '6h'}},
    {'name': '3F 電錶 (ch14) - 實功率 kW 曲線 (6h)', 'params': {'ch': 'ch14', 'field': 'kw', 'range': '6h'}},
    {'name': '3F 電錶 (ch14) - 電壓 V 曲線 (6h)', 'params': {'ch': 'ch14', 'field': 'v', 'range': '6h'}},
    {'name': '3F 電錶 (ch14) - 電流 A 曲線 (6h)', 'params': {'ch': 'ch14', 'field': 'a', 'range': '6h'}},
    {'name': '3F 電錶 (ch14) - 功率因數 PF (6h)', 'params': {'ch': 'ch14', 'field': 'pf', 'range': '6h'}},
    {'name': '全廠整合 (ch13+ch14) - 用電量柱狀 (6h)', 'params': {'ch': ['ch13', 'ch14'], 'field': 'daily_kwh', 'range': '6h'}},
    {'name': '全廠整合 (ch13+ch14) - 功率 kW 曲線 (6h)', 'params': {'ch': ['ch13', 'ch14'], 'field': 'kw', 'range': '6h'}},
    {'name': '全廠整合 (ch13+ch14) - 1日範圍 (1d)', 'params': {'ch': ['ch13', 'ch14'], 'field': 'daily_kwh', 'range': '1d'}},
]

for cfg in test_configs:
    try:
        r = requests.get(f'{BASE_URL}/api/power_chart_data', params=cfg['params'], timeout=5)
        data = r.json()
        series = data.get('series', {})
        labels = data.get('labels', [])
        is_discrete = data.get('is_discrete')
        
        info = []
        for ch, pts in series.items():
            valid_pts = [p for p in pts if p.get('v') is not None]
            val_sum = sum(p.get('v', 0) for p in valid_pts) if is_discrete else 0
            latest_v = valid_pts[-1]['v'] if valid_pts else None
            info.append(f"{ch}: {len(valid_pts)}/{len(pts)} 點 (最新={latest_v}, 累計={round(val_sum, 2) if is_discrete else '-'})")
        
        print(f"✅ [{cfg['name']}] HTTP {r.status_code}")
        print(f"   標籤數: {len(labels)} | 離散柱狀: {is_discrete}")
        print(f"   通道資料: {' | '.join(info)}")
    except Exception as e:
        print(f"❌ [{cfg['name']}] 失敗: {e}")

print('\n====================================================')
print('  測試 2: /api/power_energy_stats 能源整合統計 API')
print('====================================================')

stats_tests = [
    {'name': '1F 電錶 (ch13)', 'params': {'ch': 'ch13'}},
    {'name': '3F 電錶 (ch14)', 'params': {'ch': 'ch14'}},
    {'name': '全廠整合 (ch13 + ch14)', 'params': {'ch': ['ch13', 'ch14']}},
]

for st in stats_tests:
    try:
        r = requests.get(f'{BASE_URL}/api/power_energy_stats', params=st['params'], timeout=5)
        data = r.json()
        print(f"📊 [{st['name']}] HTTP {r.status_code}")
        print(f"   今日用電: {data.get('today_kwh')} kWh")
        print(f"   本週用電: {data.get('week_kwh')} kWh")
        print(f"   本月用電: {data.get('month_kwh')} kWh")
        print(f"   期間總用電: {data.get('period_total_kwh')} kWh")
        print(f"   尖峰/半尖峰/離峰: {data.get('period_peak_kwh')} / {data.get('period_semi_peak_kwh')} / {data.get('period_off_peak_kwh')} kWh")
        print(f"   尖峰佔比: {data.get('peak_ratio')}% | 離峰佔比: {data.get('off_peak_ratio')}%")
        print(f"   庫別能耗分佈: {json.dumps(data.get('room_distribution', {}), ensure_ascii=False)}")
        print(f"   設備運轉時數統計數: {len(data.get('device_runtimes', []))} 台設備")
    except Exception as e:
        print(f"❌ [{st['name']}] 失敗: {e}")

print('\n====================================================')
print('  測試 3: 報表查詢與 Excel 匯出 API (/api/reports/query, /api/reports/export)')
print('====================================================')

for target in ['ch13', 'ch14', 'all']:
    try:
        r = requests.get(f'{BASE_URL}/api/reports/query', params={'category': 'energy', 'target': target, 'period': 'day'}, timeout=5)
        data = r.json()
        summary = data.get('summary', {})
        records = data.get('records', [])
        print(f"📑 [日報表 JSON - {target}] HTTP {r.status_code} | 目標: {summary.get('target_name')} | 總用電量: {summary.get('consumed_kwh')} kWh | 筆數: {len(records)}")
        if records:
            latest_rec = records[-1]
            print(f"   最新一筆: 時間={latest_rec.get('time')}, kW={latest_rec.get('kw')}, kWh={latest_rec.get('kwh')}, 區間增量={latest_rec.get('delta_kwh')}")
    except Exception as e:
        print(f"❌ [日報表 JSON - {target}] 失敗: {e}")

    try:
        r_xlsx = requests.get(f'{BASE_URL}/api/reports/export', params={'category': 'energy', 'target': target, 'period': 'day'}, timeout=5)
        print(f"📥 [Excel 匯出 - {target}] HTTP {r_xlsx.status_code} | 檔案大小: {len(r_xlsx.content)} bytes")
    except Exception as e:
        print(f"❌ [Excel 匯出 - {target}] 失敗: {e}")
