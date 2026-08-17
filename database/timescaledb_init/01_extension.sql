-- 容器第一次建立時自動執行（docker-entrypoint-initdb.d）
-- 此時 app.py 建的 temperatures 等表都還不存在，這裡只先啟用擴充功能。
-- 資料表本身仍由 local_web/app.py 的 init_db() 在啟動時 CREATE TABLE IF NOT EXISTS。
-- Hypertable / 壓縮 / 保留政策要等表建立後，再執行 database/timescaledb_setup.sql。

CREATE EXTENSION IF NOT EXISTS timescaledb;
