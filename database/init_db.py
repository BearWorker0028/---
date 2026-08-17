import json
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_ROOT = BASE_DIR.parent
DB_PATH = BASE_DIR / "temperature.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
ALARM_RULES_PATH = TEMPLATE_ROOT / "collector" / "alarm_rules.json"
ALARM_RULES_EXAMPLE_PATH = TEMPLATE_ROOT / "collector" / "alarm_rules.example.json"


def init_database(db_path=DB_PATH):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        rules_path = ALARM_RULES_PATH if ALARM_RULES_PATH.exists() else ALARM_RULES_EXAMPLE_PATH
        if rules_path.exists():
            rules_data = json.loads(rules_path.read_text(encoding="utf-8"))
            rules = rules_data.get("rules", []) if isinstance(rules_data, dict) else []
            for rule in rules:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO alarm_settings
                    (channel, name, hi, lo, delay, alarm_enabled, temp_offset)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rule["channel"],
                        rule["name"],
                        rule.get("hi"),
                        rule.get("lo"),
                        int(rule.get("delay_minutes") or 0),
                        1 if rule.get("alarm_enabled", True) else 0,
                        float(rule.get("temp_offset") or 0.0),
                    ),
                )
        conn.commit()


if __name__ == "__main__":
    target_dbs = [
        DB_PATH,
        TEMPLATE_ROOT / "local_web" / "temperature.db",
    ]
    for db in target_dbs:
        init_database(db)
        print(f"Successfully initialized: {db}")

