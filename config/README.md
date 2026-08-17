# 集中化設定說明

這個資料夾放「新案場差異」的設定範本，目標是讓未來移植時少改程式、多改設定。

## 建議設定來源

1. `site_config.example.json`
   - 案場名稱、庫別、設備數量、報表欄位。
   - 可複製成 `site_config.json` 後填入新案場資料。

2. `collector/channel_config.example.json`
   - Modbus host / port、Slave ID、Register、倍率、資料型別。
   - 建議新案場複製成 `collector/channel_config.json`。

3. `collector/alarm_rules.example.json`
   - 警報上下限、延遲、開關、溫度補正。
   - 建議新案場複製成 `collector/alarm_rules.json`。

4. `.env.example`
   - 放環境變數名稱與範例值。
   - 正式密碼、token、Supabase key 不要提交到專案包。

## 移植原則

- 優先改 JSON / Excel / `.env`，不要直接改主程式。
- 若一定要改 `local_web/templates/index.html`，只改畫面配置與案場文案。
- 若一定要改 `collector/modbus_reader.py`，通常代表目前設定抽離還不夠，建議先檢查是否能放進 `channel_config.json`。
