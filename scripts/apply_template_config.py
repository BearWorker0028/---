import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build_configs():
    # 裕珍皇 12 台機器與庫別對照
    channels_def = [
        {"channel": "ch01", "name": "1F 冷凍庫 A", "slave": 1, "register": 0, "hi_temp": -15.0, "room_id": "R_1F_FREEZER"},
        {"channel": "ch02", "name": "1F 冷凍庫 B", "slave": 2, "register": 0, "hi_temp": -15.0, "room_id": "R_1F_FREEZER"},
        {"channel": "ch03", "name": "1F 冷凍庫 C", "slave": 3, "register": 0, "hi_temp": -15.0, "room_id": "R_1F_FREEZER"},
        {"channel": "ch04", "name": "1F 冷凍庫 D", "slave": 4, "register": 0, "hi_temp": -15.0, "room_id": "R_1F_FREEZER"},
        {"channel": "ch05", "name": "1F 冷凍庫 E", "slave": 5, "register": 0, "hi_temp": -15.0, "room_id": "R_1F_FREEZER"},
        {"channel": "ch06", "name": "1F 緩衝庫 A", "slave": 6, "register": 0, "hi_temp": 10.0, "room_id": "R_1F_BUFFER"},
        {"channel": "ch07", "name": "1F 碼頭區 A", "slave": 7, "register": 0, "hi_temp": 15.0, "room_id": "R_1F_DOCK"},
        {"channel": "ch08", "name": "3F 急速庫 A", "slave": 8, "register": 0, "hi_temp": -15.0, "room_id": "R_3F_BLAST"},
        {"channel": "ch09", "name": "3F 急速庫 B", "slave": 9, "register": 0, "hi_temp": -15.0, "room_id": "R_3F_BLAST"},
        {"channel": "ch10", "name": "3F 半成品庫 A", "slave": 10, "register": 0, "hi_temp": 8.0, "room_id": "R_3F_SEMI"},
        {"channel": "ch11", "name": "3F 半成品庫 B", "slave": 11, "register": 0, "hi_temp": 8.0, "room_id": "R_3F_SEMI"},
        {"channel": "ch12", "name": "3F 冷藏庫 A", "slave": 12, "register": 0, "hi_temp": 8.0, "room_id": "R_3F_COLD_ROOM"},
        {"channel": "ch13", "name": "1F 電表", "slave": 13, "register": 0, "hi_temp": None, "room_id": None},
        {"channel": "ch14", "name": "3F 電表", "slave": 14, "register": 0, "hi_temp": None, "room_id": None}
    ]


    rooms_def = [
        {
            "channel": "ch01",
            "room_id": "R_1F_FREEZER",
            "name": "1F 冷凍庫",
            "type": "freezer",
            "enabled": True,
            "temp_only_iot": False,
            "modules": [{"type": "iot627", "count": 5}],
            "floorplan": {"x": 0.15, "y": 0.25, "side": "left"}
        },
        {
            "channel": "ch06",
            "room_id": "R_1F_BUFFER",
            "name": "1F 緩衝庫",
            "type": "buffer",
            "enabled": True,
            "temp_only_iot": False,
            "modules": [{"type": "iot627", "count": 1}],
            "floorplan": {"x": 0.40, "y": 0.20, "side": "right"}
        },
        {
            "channel": "ch07",
            "room_id": "R_1F_DOCK",
            "name": "1F 碼頭區",
            "type": "dock",
            "enabled": True,
            "temp_only_iot": False,
            "modules": [{"type": "iot627", "count": 1}],
            "floorplan": {"x": 0.40, "y": 0.40, "side": "right"}
        },
        {
            "channel": "ch08",
            "room_id": "R_3F_BLAST",
            "name": "3F 急速庫",
            "type": "blast",
            "enabled": True,
            "temp_only_iot": False,
            "modules": [{"type": "iot627", "count": 2}],
            "floorplan": {"x": 0.15, "y": 0.70, "side": "left"}
        },
        {
            "channel": "ch10",
            "room_id": "R_3F_SEMI",
            "name": "3F 半成品庫",
            "type": "semi",
            "enabled": True,
            "temp_only_iot": False,
            "modules": [{"type": "iot627", "count": 2}],
            "floorplan": {"x": 0.65, "y": 0.70, "side": "right"}
        },
        {
            "channel": "ch12",
            "room_id": "R_3F_COLD_ROOM",
            "name": "3F 冷藏庫",
            "type": "cold_room",
            "enabled": True,
            "temp_only_iot": False,
            "modules": [{"type": "iot627", "count": 1}],
            "floorplan": {"x": 0.85, "y": 0.70, "side": "right"}
        }
    ]

    site_config = {
        "schema_version": "1.0",
        "site": {
            "site_id": "YJH001",
            "site_name": "裕珍皇",
            "customer_name": "裕珍皇",
            "timezone": "Asia/Taipei",
            "dashboard_title": "即時溫度監控",
            "dashboard_subtitle": "REAL-TIME TEMPERATURE DASHBOARD",
            "service_provider": "添利機械工業股份有限公司"
        },
        "runtime": {
            "api_base": "http://127.0.0.1:88",
            "data_root": "local_web",
            "publish_to_api": False,
            "mock_data_enabled": True,
            "retention_seasons": 20
        },
        "modbus": {
            "host": "192.168.1.100",
            "port": 2000,
            "framer": "RTU_OVER_TCP",
            "read_interval_seconds": 2,
            "save_interval_seconds": 60
        },
        "rooms": rooms_def,
        "channels": [
            {
                "channel": c["channel"],
                "name": c["name"],
                "slave": c["slave"],
                "register": c["register"],
                "enabled": True,
                "data_type": "int16",
                "scale": 0.1,
                "offset": 0.0,
                "invalid_below": -199.0,
                "unit": "kWh" if c["channel"] in ("ch13", "ch14") else "degC"
            } for c in channels_def
        ],
        "alarm_rules": [
            {
                "channel": c["channel"],
                "name": c["name"],
                "hi": c["hi_temp"],
                "lo": None,
                "delay_minutes": 5,
                "alarm_enabled": c["hi_temp"] is not None,
                "temp_offset": 0.0
            } for c in channels_def
        ],
        "reports": {
            "default_enabled": True,
            "fields": ["avg_temp", "temp_control", "current", "kw", "kwh"]
        },
        "assets": {
            "logo": "local_web/static/mackerel_logo.png",
            "line_qr": "local_web/static/line_qr.png",
            "floorplan": "local_web/static/floorplan.png"
        },
        "remote_dashboard": {
            "enabled": False,
            "provider": "supabase_vercel",
            "notes": "遠端儀表板為選配；本地電視牆可不啟用。"
        }
    }

    # 輸出 config/site_config.json
    config_dir = ROOT / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    site_config_path = config_dir / "site_config.json"
    site_config_path.write_text(json.dumps(site_config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated: {site_config_path}")

    # 輸出 collector/channel_config.json
    collector_dir = ROOT / "collector"
    collector_dir.mkdir(parents=True, exist_ok=True)
    channel_config = {
        "site_id": "YJH001",
        "site_name": "裕珍皇",
        "modbus": site_config["modbus"],
        "channels": site_config["channels"]
    }
    channel_config_path = collector_dir / "channel_config.json"
    channel_config_path.write_text(json.dumps(channel_config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated: {channel_config_path}")

    # 輸出 collector/alarm_rules.json
    alarm_rules = {
        "site_id": "YJH001",
        "default_cooldown_seconds": 600,
        "notification_channels": {
            "pushover": {
                "enabled": False,
                "token_env": "PUSHOVER_TOKEN",
                "user_env": "PUSHOVER_USER"
            },
            "line_messaging_api": {
                "enabled": False,
                "channel_access_token_env": "LINE_CHANNEL_ACCESS_TOKEN",
                "target_ids": []
            }
        },
        "rules": site_config["alarm_rules"]
    }
    alarm_rules_path = collector_dir / "alarm_rules.json"
    alarm_rules_path.write_text(json.dumps(alarm_rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated: {alarm_rules_path}")

if __name__ == "__main__":
    build_configs()
