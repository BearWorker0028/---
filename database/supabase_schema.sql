-- ============================================================
-- 裕珍皇中央監控系統 - Supabase 即時狀態表
-- 依據 docs/監控位址表.md、docs/IoT627_監控點位對照表.md、
-- docs/電錶監控位址與參數對照表.md 之點位定義設計
--
-- 溫控 (IoT-627) 與電表 (SPM-3) 為不同模組、不同前端視窗，
-- 因此拆成兩張獨立資料表，欄位各自對應實際點位，不互相污染。
-- ============================================================

-- ── 一、溫控器狀態表 (IoT-627：冷凍庫/緩衝庫/碼頭區) ──
DROP TABLE IF EXISTS gw1_temp_status;

CREATE TABLE gw1_temp_status (
    channel         VARCHAR(10) PRIMARY KEY,           -- 點位通道 (ch01~ch12)
    device_name     VARCHAR(64) NOT NULL,               -- 設備名稱 (如 1F 冷凍庫 A)
    updated_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Taipei'),  -- 最後更新時間 (台灣時間)

    set_temp               NUMERIC(5,1),   -- 設定溫度 °C
    control_temp            NUMERIC(5,1),   -- 控制溫度 (庫溫) °C
    coil_temp                NUMERIC(5,1),   -- 盤管溫度 °C
    return_temp              NUMERIC(5,1),   -- 回流管溫度 °C
    low_pressure              NUMERIC(6,1),   -- 低壓 bar
    high_pressure              NUMERIC(6,1),   -- 高壓 bar
    compressor_current          NUMERIC(5,1),   -- 壓縮機電流 A
    defrost_current              NUMERIC(5,1),   -- 除霜電流 A
    fault_code                    INTEGER,        -- 原始狀態位元值 (40035, 供除錯用)

    status_running                BOOLEAN,        -- Bit0 運轉中
    status_defrost                 BOOLEAN,        -- Bit1 除霜中
    status_drip                     BOOLEAN,        -- Bit2 滴水延遲中
    status_fan_delay                 BOOLEAN,        -- Bit3 風機延遲中
    status_high_temp_alarm            BOOLEAN,        -- Bit4 高溫警報
    status_low_temp_alarm              BOOLEAN,        -- Bit5 低溫警報
    status_defrost_heater                BOOLEAN,        -- Bit6 除霜電熱啟動
    status_fan                            BOOLEAN,        -- Bit7 風機運轉中
    status_cooling                          BOOLEAN,        -- Bit8 壓縮機製冷中
    status_phase_err                             BOOLEAN,        -- Bit11 (L212) L212設備異常
    status_sensor_err                              BOOLEAN,        -- Bit12 (L213) 感溫頭故障
    status_overload_err                              BOOLEAN,        -- Bit13 (L214) 馬達積熱過載
    status_door_open                                   BOOLEAN,        -- Bit14 (L215) 庫門開啟中
    status_equip_err                                     BOOLEAN,        -- Bit15 (L216) L216設備異常

    raw_data        JSONB           -- 原始 Modbus 暫存器數值 (供除錯追溯)
);

CREATE INDEX idx_gw1_temp_status_updated_at ON gw1_temp_status (updated_at);

ALTER TABLE gw1_temp_status ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow Service Role Full Access"
ON gw1_temp_status FOR ALL
USING (true);

-- ── 二、電表狀態表 (SPM-3：集合式電力品質電錶) ──
DROP TABLE IF EXISTS gw1_meter_status;

CREATE TABLE gw1_meter_status (
    channel         VARCHAR(10) PRIMARY KEY,           -- 點位通道 (ch13~ch14)
    device_name     VARCHAR(64) NOT NULL,               -- 設備名稱 (如 1F 集合式電錶)
    updated_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Taipei'),  -- 最後更新時間 (台灣時間)

    voltage_rs      NUMERIC(6,2),   -- RS/AB 線電壓 V
    voltage_st      NUMERIC(6,2),   -- ST/BC 線電壓 V
    voltage_tr      NUMERIC(6,2),   -- TR/CA 線電壓 V
    voltage_avg     NUMERIC(6,2),   -- 平均線電壓 V
    frequency       NUMERIC(5,2),   -- 電網頻率 Hz
    current_r       NUMERIC(7,2),   -- R相電流 A
    current_s       NUMERIC(7,2),   -- S相電流 A
    current_t       NUMERIC(7,2),   -- T相電流 A
    current_avg     NUMERIC(7,2),   -- 平均電流 A
    power_total     NUMERIC(9,2),   -- 總有效功率 kW
    power_factor    NUMERIC(4,2),   -- 功率因數
    reactive_power  NUMERIC(9,2),   -- 總無功功率 kVAR
    apparent_power  NUMERIC(9,2),   -- 總視在功率 kVA
    energy_total    NUMERIC(14,2),  -- 總累積用電量 kWh

    raw_data        JSONB           -- 原始 Modbus 暫存器數值 (供除錯追溯)
);

CREATE INDEX idx_gw1_meter_status_updated_at ON gw1_meter_status (updated_at);

ALTER TABLE gw1_meter_status ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow Service Role Full Access"
ON gw1_meter_status FOR ALL
USING (true);

-- ============================================================
-- 三、GW2 溫控器狀態表 (3F：半成品冷凍 / 急速庫 / 冷藏庫)
-- ============================================================
DROP TABLE IF EXISTS gw2_temp_status;

CREATE TABLE gw2_temp_status (
    channel         VARCHAR(10) PRIMARY KEY,           -- 點位通道 (ch08, ch09, ch10, ch11, ch12)
    device_name     VARCHAR(64) NOT NULL,               -- 設備名稱 (如 3F 半成品冷凍 A)
    updated_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Taipei'),  -- 最後更新時間 (台灣時間)

    set_temp               NUMERIC(5,1),   -- 設定溫度 °C
    control_temp            NUMERIC(5,1),   -- 控制溫度 (庫溫) °C
    coil_temp                NUMERIC(5,1),   -- 盤管溫度 °C
    return_temp              NUMERIC(5,1),   -- 回流管溫度 °C
    low_pressure              NUMERIC(6,1),   -- 低壓 bar
    high_pressure              NUMERIC(6,1),   -- 高壓 bar
    compressor_current          NUMERIC(5,1),   -- 壓縮機電流 A
    defrost_current              NUMERIC(5,1),   -- 除霜電流 A
    fault_code                    INTEGER,        -- 原始狀態位元值 (40035, 供除錯用)

    status_running                BOOLEAN,        -- Bit0 運轉中
    status_defrost                 BOOLEAN,        -- Bit1 除霜中
    status_drip                     BOOLEAN,        -- Bit2 滴水延遲中
    status_fan_delay                 BOOLEAN,        -- Bit3 風機延遲中
    status_high_temp_alarm            BOOLEAN,        -- Bit4 高溫警報
    status_low_temp_alarm              BOOLEAN,        -- Bit5 低溫警報
    status_defrost_heater                BOOLEAN,        -- Bit6 除霜電熱啟動
    status_fan                            BOOLEAN,        -- Bit7 風機運轉中
    status_cooling                          BOOLEAN,        -- Bit8 壓縮機製冷中
    status_phase_err                             BOOLEAN,        -- Bit11 (L212) L212設備異常
    status_sensor_err                              BOOLEAN,        -- Bit12 (L213) 感溫頭故障
    status_overload_err                              BOOLEAN,        -- Bit13 (L214) 馬達積熱過載
    status_door_open                                   BOOLEAN,        -- Bit14 (L215) 庫門開啟中
    status_equip_err                                     BOOLEAN,        -- Bit15 (L216) L216設備異常

    raw_data        JSONB           -- 原始 Modbus 暫存器數值 (供除錯追溯)
);

CREATE INDEX idx_gw2_temp_status_updated_at ON gw2_temp_status (updated_at);

ALTER TABLE gw2_temp_status ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow Service Role Full Access"
ON gw2_temp_status FOR ALL
USING (true);

-- ============================================================
-- 四、GW2 電表狀態表 (3F：SPM-3 集合式電力品質電錶)
-- ============================================================
DROP TABLE IF EXISTS gw2_meter_status;

CREATE TABLE gw2_meter_status (
    channel         VARCHAR(10) PRIMARY KEY,           -- 點位通道 (ch14)
    device_name     VARCHAR(64) NOT NULL,               -- 設備名稱 (如 3F 集合式電錶)
    updated_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Taipei'),  -- 最後更新時間 (台灣時間)

    voltage_rs      NUMERIC(6,2),   -- RS/AB 線電壓 V
    voltage_st      NUMERIC(6,2),   -- ST/BC 線電壓 V
    voltage_tr      NUMERIC(6,2),   -- TR/CA 線電壓 V
    voltage_avg     NUMERIC(6,2),   -- 平均線電壓 V
    frequency       NUMERIC(5,2),   -- 電網頻率 Hz
    current_r       NUMERIC(7,2),   -- R相電流 A
    current_s       NUMERIC(7,2),   -- S相電流 A
    current_t       NUMERIC(7,2),   -- T相電流 A
    current_avg     NUMERIC(7,2),   -- 平均電流 A
    power_total     NUMERIC(9,2),   -- 總有效功率 kW
    power_factor    NUMERIC(4,2),   -- 功率因數
    reactive_power  NUMERIC(9,2),   -- 總無功功率 kVAR
    apparent_power  NUMERIC(9,2),   -- 總視在功率 kVA
    energy_total    NUMERIC(14,2),  -- 總累積用電量 kWh

    raw_data        JSONB           -- 原始 Modbus 暫存器數值 (供除錯追溯)
);

CREATE INDEX idx_gw2_meter_status_updated_at ON gw2_meter_status (updated_at);

ALTER TABLE gw2_meter_status ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow Service Role Full Access"
ON gw2_meter_status FOR ALL
USING (true);

