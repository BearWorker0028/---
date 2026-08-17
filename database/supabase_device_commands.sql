-- ============================================================
-- 裕珍皇中央監控系統 - 遠端設備控制命令佇列
--
-- 前端（app.py）寫入 pending 命令 → GCP 上的 gw1_supabase_collector.py
-- 定期輪詢本表，透過既有的 W610 Modbus TCP 連線執行寫入，再回報結果。
--
-- 這是獨立檔案，只新增 device_commands 一張表，不含 DROP TABLE，
-- 避免誤執行到 supabase_schema.sql 清空現有正式資料表。
-- ============================================================

CREATE TABLE IF NOT EXISTS device_commands (
    id              BIGSERIAL PRIMARY KEY,
    channel         VARCHAR(10) NOT NULL,              -- 目標通道 (如 ch07)
    command_type    VARCHAR(32) NOT NULL,               -- 命令類型 (目前僅 set_temperature)
    value            NUMERIC(6,2),                       -- 命令數值 (依 command_type 意義不同)
    status            VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending / success / failed
    error_message      TEXT,
    created_at            TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Taipei'),
    executed_at             TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_device_commands_status ON device_commands (status, created_at);
CREATE INDEX IF NOT EXISTS idx_device_commands_channel ON device_commands (channel, created_at DESC);

ALTER TABLE device_commands ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow Service Role Full Access"
ON device_commands FOR ALL
USING (true);
