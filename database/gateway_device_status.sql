-- ============================================================
-- 裕珍皇中央監控系統 - 網關與設備連線診斷表 (Gateway & Device Status)
-- ============================================================

-- ── 1. 網關連線狀態表 (Gateway Status) ──
CREATE TABLE IF NOT EXISTS gateway_status (
    gateway_id      VARCHAR(16) PRIMARY KEY,           -- 'GW1', 'GW2'
    gateway_name    VARCHAR(64) NOT NULL,              -- '1F 網關 (GW1)', '3F 網關 (GW2)'
    is_online       BOOLEAN NOT NULL DEFAULT FALSE,    -- 網關 TCP 是否連線中
    client_ip       VARCHAR(45),                       -- 現場連入之公網 IP / 通訊埠
    port            INTEGER,                           -- 連線 Port (8801, 1883)
    last_heartbeat  TIMESTAMP WITH TIME ZONE,          -- 最新心跳或應答時間
    error_message   TEXT,                              -- 異常或斷線訊息
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE gateway_status ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow Full Access to gateway_status" ON gateway_status;
CREATE POLICY "Allow Full Access to gateway_status" ON gateway_status FOR ALL USING (true);

-- 初始化 GW1 與 GW2 種子資料
INSERT INTO gateway_status (gateway_id, gateway_name, is_online, port, error_message)
VALUES 
    ('GW1', '1F 網關 (GW1)', false, 8801, '等待初次連線'),
    ('GW2', '3F 網關 (GW2)', false, 1883, '等待初次連線')
ON CONFLICT (gateway_id) DO UPDATE 
SET gateway_name = EXCLUDED.gateway_name, port = EXCLUDED.port;


-- ── 2. 從機設備狀態表 (Device Status) ──
CREATE TABLE IF NOT EXISTS device_status (
    gateway_id      VARCHAR(16) NOT NULL,              -- 'GW1', 'GW2'
    slave_id        INTEGER NOT NULL,                  -- Modbus 站號 ID
    channel         VARCHAR(10) NOT NULL,              -- 點位通道 (ch01~ch14)
    device_name     VARCHAR(64) NOT NULL,              -- 設備名稱 (如 1F 冷凍庫 A)
    device_type     VARCHAR(16) NOT NULL,              -- 'IoT-627', 'SPM-3'
    is_online       BOOLEAN NOT NULL DEFAULT FALSE,    -- 設備是否正常通訊
    fault_code      INTEGER DEFAULT 0,                 -- 故障碼
    last_response   TIMESTAMP WITH TIME ZONE,          -- 最後成功收到封包時間
    error_message   TEXT,                              -- 異常資訊 (如 Timeout)
    consecutive_timeouts INTEGER DEFAULT 0,            -- 連續逾時次數
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (gateway_id, slave_id)
);

CREATE INDEX IF NOT EXISTS idx_device_status_channel ON device_status (channel);

ALTER TABLE device_status ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow Full Access to device_status" ON device_status;
CREATE POLICY "Allow Full Access to device_status" ON device_status FOR ALL USING (true);

-- 初始化 14 個設備種子資料
INSERT INTO device_status (gateway_id, slave_id, channel, device_name, device_type, is_online)
VALUES
    ('GW1', 1, 'ch01', '1F 冷凍庫 A', 'IoT-627', false),
    ('GW1', 2, 'ch02', '1F 冷凍庫 B', 'IoT-627', false),
    ('GW1', 3, 'ch03', '1F 冷凍庫 C', 'IoT-627', false),
    ('GW1', 4, 'ch04', '1F 冷凍庫 D', 'IoT-627', false),
    ('GW1', 5, 'ch05', '1F 冷凍庫 E', 'IoT-627', false),
    ('GW1', 6, 'ch06', '1F 緩衝庫 A', 'IoT-627', false),
    ('GW1', 7, 'ch07', '1F 碼頭區 A', 'IoT-627', false),
    ('GW1', 8, 'ch13', '1F 集合式電錶', 'SPM-3', false),
    ('GW2', 11, 'ch10', '3F 半成品冷凍 A', 'IoT-627', false),
    ('GW2', 12, 'ch11', '3F 半成品冷凍 B', 'IoT-627', false),
    ('GW2', 13, 'ch08', '3F 急速庫 20HP', 'IoT-627', false),
    ('GW2', 14, 'ch09', '3F 急速庫 10HP', 'IoT-627', false),
    ('GW2', 15, 'ch12', '3F 冷藏庫', 'IoT-627', false),
    ('GW2', 16, 'ch14', '3F 集合式電錶', 'SPM-3', false)
ON CONFLICT (gateway_id, slave_id) DO UPDATE
SET channel = EXCLUDED.channel, device_name = EXCLUDED.device_name, device_type = EXCLUDED.device_type;
