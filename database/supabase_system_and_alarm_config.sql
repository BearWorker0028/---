-- ============================================================
-- 裕珍皇中央監控系統 - 雲端設定雙向同步表 (Supabase)
-- 
-- 用途：
-- 1. system_config: 儲存 LINE 官方帳號 Token、通知 Target ID、推播冷卻時間等全域系統設定。
-- 2. room_alarm_settings: 儲存各庫別警報門檻 (Hi/Lo)、警報延遲時間、啟用狀態、溫度補償。
-- 
-- 執行方式：
-- 請登入 Supabase 控制台 (https://supabase.com/dashboard)
-- 進入 SQL Editor，貼上本檔案全部內容並點擊 Run 執行即可。
-- ============================================================

-- ── 1. 系統全域設定表 ──
CREATE TABLE IF NOT EXISTS system_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Taipei')
);

ALTER TABLE system_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow Full Access to system_config" ON system_config;
CREATE POLICY "Allow Full Access to system_config" ON system_config FOR ALL USING (true);

-- ── 2. 庫房警報門檻設定表 ──
CREATE TABLE IF NOT EXISTS room_alarm_settings (
    room_id         VARCHAR(32) PRIMARY KEY,
    name            VARCHAR(64) NOT NULL,
    channels        TEXT NOT NULL,
    hi              NUMERIC(5,1),
    lo              NUMERIC(5,1),
    delay           INTEGER DEFAULT 10,
    alarm_enabled   INTEGER DEFAULT 1,
    temp_offset     NUMERIC(4,1) DEFAULT 0.0,
    updated_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Taipei')
);

ALTER TABLE room_alarm_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow Full Access to room_alarm_settings" ON room_alarm_settings;
CREATE POLICY "Allow Full Access to room_alarm_settings" ON room_alarm_settings FOR ALL USING (true);

-- ── 3. 通道與運轉電流閥值設定表 (包含運轉電流閥值與 NFB 額定電流) ──
CREATE TABLE IF NOT EXISTS alarm_settings (
    channel                 VARCHAR(16) PRIMARY KEY,
    name                    VARCHAR(64) NOT NULL,
    hi                      NUMERIC(5,1),
    lo                      NUMERIC(5,1),
    delay                   INTEGER DEFAULT 0,
    alarm_enabled           INTEGER DEFAULT 1,
    temp_offset             NUMERIC(4,1) DEFAULT 0.0,
    current_threshold       NUMERIC(5,2) DEFAULT 0.5,
    nfb_rated_current       NUMERIC(6,1),
    power_anomaly_threshold NUMERIC(5,1) DEFAULT 15.0,
    updated_at              TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Taipei')
);

ALTER TABLE alarm_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow Full Access to alarm_settings" ON alarm_settings;
CREATE POLICY "Allow Full Access to alarm_settings" ON alarm_settings FOR ALL USING (true);
