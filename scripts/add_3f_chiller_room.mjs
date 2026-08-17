import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const ROOT = "C:/tmp/YJH_monitoring_site_template";
const XLSX = path.join(ROOT, "inputs", "裕珍皇_案場輸入總表.xlsx");
const OUTPUT_JSON = path.join(ROOT, "outputs", "site_config_initial.json");
const GAP_REPORT = path.join(ROOT, "docs", "裕珍皇_缺漏清單.md");
const PREVIEW_DIR = path.join(ROOT, "docs", "previews_after_chiller");

const additions = {
  "02_庫別": {
    idCol: "room_id",
    id: "R_3F_CHILLER",
    row: ["R_3F_CHILLER", "YJH001", "3F 冷藏庫", "冷藏", "待確認", "待確認", 1, "FP_3F", "3F 冷藏庫，對應 A 主機"],
  },
  "03_主機": {
    idCol: "machine_id",
    id: "M_3F_CHILLER_A",
    row: ["M_3F_CHILLER_A", "R_3F_CHILLER", "3F 冷藏庫 A", "冷藏主機待確認", "待確認", "待確認", "待確認", "待確認", "C_3F_CHILLER_A", "", "待確認", "補充新增：第 12 台主機"],
  },
  "04_溫控器": {
    idCol: "controller_id",
    id: "C_3F_CHILLER_A",
    row: ["C_3F_CHILLER_A", "M_3F_CHILLER_A", "IoT627", "待確認", "Modbus RTU", "待確認", "待確認", "待確認", 8, "待確認", "待提供", "待確認", "第 12 台主機對應 1 台 IoT627；站號/通訊參數待確認"],
  },
  "08_點位表": {
    idCol: "point_id",
    id: "P_3F_CHILLER_A_CTRL_TEMP",
    row: ["P_3F_CHILLER_A_CTRL_TEMP", "YJH001", "R_3F_CHILLER", "M_3F_CHILLER_A", "C_3F_CHILLER_A", "controller", "待點位表確認", "控制溫度", "temperature", "待確認", "", "待確認", "待確認", 0, "degC", "R", 30, "", "待確認", "待確認", "Y", "Y", "由 IoT627 點位表補齊"],
  },
  "10_告警": {
    idCol: "alarm_id",
    id: "A_M_3F_CHILLER_A_HIGH_TEMP",
    row: ["A_M_3F_CHILLER_A_HIGH_TEMP", "P_3F_CHILLER_A_CTRL_TEMP", "3F 冷藏庫 A 高溫", "critical", ">", "待確認", "待確認", "待確認", "N_YJH_OPS", "Y", "溫度門檻待確認"],
  },
  "12_平面圖": {
    idCol: "object_id",
    id: "OBJ_R_3F_CHILLER",
    row: ["FP_3F", "待提供_3F平面圖", "rooms", "OBJ_R_3F_CHILLER", "room", "R_3F_CHILLER", "待確認", "待確認", "待確認", "待確認", "green", "red", "待由平面圖標註"],
  },
  "13_Dashboard": {
    idCol: "view_id",
    id: "V_3F_CHILLER_A_TEMP",
    row: ["V_3F_CHILLER_A_TEMP", "3F 冷藏庫 A 溫度卡", "point_card", "M_3F_CHILLER_A", "P_3F_CHILLER_A_CTRL_TEMP", 120, "Y", "Y", "24h", "admin;operator;viewer", "補充新增"],
  },
  "15_檢核清單": {
    idCol: "item_id",
    id: "CHK_YJH_006",
    row: ["CHK_YJH_006", "庫別/主機", "確認 3F 冷藏庫 A 主機與 IoT627 配線/站號", "工程師", "Y", "todo", "", "補充新增"],
  },
};

function rectangular(values) {
  const max = Math.max(...values.map((row) => row.length));
  return values.map((row) => [...row, ...Array(max - row.length).fill("")]);
}

function normalize(value) {
  return String(value ?? "").trim();
}

function getSheetRows(workbook, sheetName) {
  const ws = workbook.worksheets.getItem(sheetName);
  const used = ws.getUsedRange(true);
  return rectangular(used.values);
}

function setWholeSheet(workbook, sheetName, rows) {
  const ws = workbook.worksheets.getItem(sheetName);
  const oldUsed = ws.getUsedRange(true);
  const oldRows = oldUsed.values.length;
  const oldCols = Math.max(...oldUsed.values.map((row) => row.length));
  oldUsed.clear({ applyTo: "contents" });
  const next = rectangular(rows);
  ws.getRangeByIndexes(0, 0, next.length, next[0].length).values = next;
  if (next.length < oldRows) {
    ws.getRangeByIndexes(next.length, 0, oldRows - next.length, oldCols).clear({ applyTo: "contents" });
  }
}

function appendIfMissing(workbook, sheetName, spec) {
  const rows = getSheetRows(workbook, sheetName);
  const headers = rows[0].map(normalize);
  const idIndex = headers.indexOf(spec.idCol);
  if (idIndex < 0) throw new Error(`${sheetName}: missing ${spec.idCol}`);
  if (rows.slice(1).some((row) => normalize(row[idIndex]) === spec.id)) {
    return false;
  }
  const width = headers.length;
  const row = [...spec.row, ...Array(width - spec.row.length).fill("")].slice(0, width);
  rows.push(row);
  setWholeSheet(workbook, sheetName, rows);
  return true;
}

function updateReadme(workbook) {
  const rows = getSheetRows(workbook, "README");
  for (const row of rows) {
    if (normalize(row[0]) === "目前資料狀態") {
      row[1] = "已填案場、6 個庫別、12 台主機、12 台 IoT627、2 台電表骨架；其餘標示待確認";
    }
    if (normalize(row[0]) === "下一步") {
      row[1] = "補溫控器站號/通訊參數、電表規格、Gateway/MQTT、點位表、平面圖；特別確認 3F 冷藏庫 A";
    }
  }
  setWholeSheet(workbook, "README", rows);
}

function updateChecklistText(workbook) {
  const rows = getSheetRows(workbook, "15_檢核清單");
  const headers = rows[0].map(normalize);
  const itemIdx = headers.indexOf("item_id");
  const checkIdx = headers.indexOf("check_item");
  for (const row of rows.slice(1)) {
    if (normalize(row[itemIdx]) === "CHK_YJH_002") {
      row[checkIdx] = "確認 12 台 IoT627 型號、站號、通訊參數";
    }
  }
  setWholeSheet(workbook, "15_檢核清單", rows);
}

function extractTables(workbook) {
  const tables = {};
  for (const sheet of workbook.worksheets.items) {
    if (sheet.name === "README") continue;
    const rows = getSheetRows(workbook, sheet.name);
    const headers = rows[0].map(normalize);
    tables[sheet.name] = rows.slice(1)
      .map((row) => Object.fromEntries(headers.map((h, i) => [h, row[i] ?? ""])))
      .filter((row) => Object.values(row).some((v) => normalize(v) !== ""));
  }
  return tables;
}

async function writeConfig(workbook) {
  const payload = {
    generated_at: new Date().toISOString().slice(0, 19),
    site_id: "YJH001",
    site_name: "裕珍皇",
    status: "initial_skeleton_updated_3f_chiller",
    tables: extractTables(workbook),
  };
  await fs.writeFile(OUTPUT_JSON, JSON.stringify(payload, null, 2), "utf8");
}

async function writeGapReport() {
  const lines = [
    "# 裕珍皇案場缺漏清單",
    "",
    "## 已建立",
    "",
    "- 案場：裕珍皇",
    "- 地址：高雄市茄萣區莒光路三段288-10號",
    "- 庫別：1F 冷凍庫、1F 緩衝庫、1F 碼頭區、3F 急速庫、3F 半成品庫、3F 冷藏庫",
    "- 主機：12 台",
    "- 溫控器：12 台 IoT627，每台主機 1 台",
    "- 數位電表：1F CP-1、3F CP-3",
    "",
    "## 待確認",
    "",
    "- 每個庫別的目標溫度範圍，包含 3F 冷藏庫",
    "- 12 台 IoT627 的完整型號、RS485 站號、baud rate、parity、stop bit",
    "- IoT627 點位表或 Modbus register table",
    "- 主機品牌、型號、HP、冷媒",
    "- 數位電表品牌、型號、相別、CT/PT、站號、通訊參數、量測項目",
    "- Gateway 型號、MAC、IP、MQTT host/port/TLS/topic",
    "- 偵測器設備：門磁、溫濕度、壓力、電流、漏水等是否需要",
    "- 1F/3F 平面圖檔與設備座標，包含 3F 冷藏庫位置",
    "- 告警門檻、延遲時間、通知對象",
  ];
  await fs.writeFile(GAP_REPORT, `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  await fs.mkdir(PREVIEW_DIR, { recursive: true });
  const input = await FileBlob.load(XLSX);
  const workbook = await SpreadsheetFile.importXlsx(input);

  const before = await workbook.inspect({
    kind: "sheet,table",
    maxChars: 5000,
    tableMaxRows: 4,
    tableMaxCols: 5,
  });
  await fs.writeFile(path.join(ROOT, "docs", "before_add_3f_chiller.inspect.ndjson"), before.ndjson, "utf8");

  for (const [sheetName, spec] of Object.entries(additions)) {
    appendIfMissing(workbook, sheetName, spec);
  }
  updateReadme(workbook);
  updateChecklistText(workbook);

  const errorScan = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
    summary: "formula error scan",
  });
  await fs.writeFile(path.join(ROOT, "docs", "after_add_3f_chiller_error_scan.ndjson"), errorScan.ndjson, "utf8");

  for (const sheetName of ["02_庫別", "03_主機", "04_溫控器", "08_點位表", "10_告警", "13_Dashboard"]) {
    const preview = await workbook.render({
      sheetName,
      autoCrop: "all",
      scale: 1,
      format: "png",
    });
    await fs.writeFile(path.join(PREVIEW_DIR, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
  }

  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(XLSX);
  await writeConfig(workbook);
  await writeGapReport();

  const tables = extractTables(workbook);
  console.log(JSON.stringify({
    rooms: tables["02_庫別"].length,
    machines: tables["03_主機"].length,
    controllers: tables["04_溫控器"].length,
    meters: tables["06_電表"].length,
    points: tables["08_點位表"].length,
    alarms: tables["10_告警"].length,
  }, null, 2));
}

await main();
