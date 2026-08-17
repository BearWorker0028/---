# 精簡版專案包使用說明

這個資料夾是給 AI 分析與移植案場用的精簡版，不是完整備份。

## 主系統架構

```text
Modbus / RS485 設備
  ↓
collector/modbus_reader.py
  ↓
local_web/app.py
  ↓
local_web/templates/*.html + local_web/static/*
```

## 建議 AI 先讀順序

1. `AI_使用說明.md`
2. `docs/模板包瘦身與設定集中化.md`
3. `docs/新案場資料必填清單.md`
4. `config/site_config.example.json`
5. `collector/channel_config.example.json`
6. `collector/alarm_rules.example.json`
7. `collector/modbus_reader.py`
8. `local_web/app.py`
9. `local_web/templates/index.html`
10. `docs/通道對照表.xlsx`
11. `docs/施工設定表.xlsx`
12. `docs/系統架構圖.html`

## 主要檔案用途

- `collector/modbus_reader.py`：Modbus TCP/RTU 資料採集、倍率轉換、警報判斷、寫入資料庫或發布到後端。
- `local_web/app.py`：Flask 後端、API、資料庫初始化、歷史查詢、報表下載、電視牆頁面路由。
- `local_web/templates/index.html`：本地電視牆主畫面，包含大部分 HTML/CSS/JS 即時顯示邏輯。
- `local_web/templates/remote.html`：遠端簡化檢視頁。
- `local_web/static/*`：Logo、QR code、平面圖等畫面素材。
- `database/schema.sql`：資料表結構參考。
- `database/init_db.py`：資料庫初始化參考。
- `docs/*.xlsx`：點位、通訊與施工設定資料。
- `config/site_config.example.json`：新案場集中設定範本，描述案場、庫別、設備、平面圖、報表欄位。
- `.env.example`：環境變數範本，正式 token / 密碼 / key 不要寫死在程式內。
- `tools/site_input_builder.py`：通用新案場回填表產生工具，取代 `tmp` 內特定案場腳本的角色。
- `tools/build_clean_template.py`：產生乾淨模板包，排除暫存、舊案場輸出、node_modules、資料庫與敏感 env。
- `remote_dashboard_選配/*`：遠端雲端儀表板的部署參考，非本地電視牆必要檔。
- `tmp/*`：歷史案場或實驗產物。保留作參考，但不應放進乾淨模板包。

## 已排除內容

- 執行中的 `.db` / `.sqlite` 資料庫
- `__pycache__`
- log
- `tmp/` 舊案場與實驗輸出
- `outputs/` 工具產物
- `node_modules/` 與 runtime 快取
- DWG / BAK / 大型圖資備份
- 測試輸出與暫存 PDF 文字
- 原始案場可能含敏感資訊的真實金鑰

可用下列工具產生乾淨包：

```powershell
C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\build_clean_template.py
```

可用下列工具建立新案場回填表：

```powershell
C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\site_input_builder.py --site-id NEW001 --site-name 新案場名稱 --rooms "冷藏庫:2:冷藏,冷凍庫:1:冷凍"
```

## 移植到新案場時通常要改

- Modbus 主機 IP、Port、Slave ID
- register 位址、倍率、資料型別
- 點位名稱與區域配置
- 警報上下限、延遲、推播方式
- 平面圖與圖控座標
- 冷凍庫、電表、IoT 控制器數量
- 報表欄位與顯示名稱

## 注意

`collector/modbus_reader.py` 在這份精簡包內已將推播 token/user 改成環境變數：

```text
PUSHOVER_TOKEN
PUSHOVER_USER
MODBUS_HOST
MODBUS_PORT
API_BASE
PUBLISH_TO_API
DATABASE_URL
```

請不要把正式密碼、token、Supabase service role key 或內網帳密交給外部 AI。
