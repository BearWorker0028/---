CREATE TABLE IF NOT EXISTS temperatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    channel TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    status TEXT DEFAULT 'NORMAL'
);

CREATE INDEX IF NOT EXISTS idx_temperatures_channel_time
ON temperatures (channel, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_temperatures_time
ON temperatures (timestamp DESC);

CREATE TABLE IF NOT EXISTS alarm_settings (
    channel TEXT PRIMARY KEY,
    name TEXT,
    hi REAL,
    lo REAL,
    delay INTEGER DEFAULT 0,
    alarm_enabled INTEGER DEFAULT 1,
    temp_offset REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS alarm_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_at TEXT,
    channel TEXT,
    name TEXT,
    value REAL,
    alarm_type TEXT,
    hi REAL,
    lo REAL
);

CREATE INDEX IF NOT EXISTS idx_alarm_history_time
ON alarm_history (triggered_at DESC);

CREATE INDEX IF NOT EXISTS idx_alarm_history_channel_time
ON alarm_history (channel, triggered_at DESC);

CREATE TABLE IF NOT EXISTS power_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    channel TEXT,
    v REAL,
    a REAL,
    kw REAL,
    pf REAL,
    kwh REAL
);

CREATE TABLE IF NOT EXISTS monitoring_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    site_code TEXT NOT NULL,
    device_no TEXT NOT NULL,
    data_key TEXT NOT NULL,
    data_value REAL
);

CREATE INDEX IF NOT EXISTS idx_monitoring_logs_timestamp ON monitoring_logs (timestamp);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_device_no_key ON monitoring_logs (device_no, data_key);

