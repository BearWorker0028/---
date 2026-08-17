-- ============================================================
-- 裕珍皇地端 TimescaleDB 二次設定
-- 先跑過一次 local_web/app.py（讓它的 init_db() 建好
-- temperatures / alarm_settings / alarm_history / monitoring_logs /
-- power_readings 這幾張表），再執行本檔案。
--
-- 執行方式（Docker 容器內）：
--   docker exec -i yjh_timescaledb psql -U yjh_user -d yjh_timeseries < database/timescaledb_setup.sql
-- ============================================================

-- ── 溫度主表：轉為 Hypertable（依時間自動分區）──
-- TimescaleDB 要求唯一索引/主鍵必須包含分區欄位(timestamp)，
-- 原本 id BIGSERIAL PRIMARY KEY 只有 id，需先改成複合主鍵。
ALTER TABLE temperatures DROP CONSTRAINT IF EXISTS temperatures_pkey;

SELECT create_hypertable(
    'temperatures', 'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

ALTER TABLE temperatures ADD PRIMARY KEY (id, timestamp);

-- 7 天前的資料自動壓縮（省空間，2 年保留期下比 30 天更快回收空間）
ALTER TABLE temperatures SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'channel',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('temperatures', INTERVAL '7 days', if_not_exists => TRUE);

-- 保留 2 年，超過自動刪除舊 chunk
SELECT add_retention_policy('temperatures', INTERVAL '2 years', if_not_exists => TRUE);

-- ── monitoring_logs（報表用的逐點紀錄）：同樣轉為 Hypertable ──
ALTER TABLE monitoring_logs DROP CONSTRAINT IF EXISTS monitoring_logs_pkey;

SELECT create_hypertable(
    'monitoring_logs', 'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

ALTER TABLE monitoring_logs ADD PRIMARY KEY (id, timestamp);

ALTER TABLE monitoring_logs SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_no, data_key',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('monitoring_logs', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('monitoring_logs', INTERVAL '2 years', if_not_exists => TRUE);

-- ── 驗證 ──
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;
