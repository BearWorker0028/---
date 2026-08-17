import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const ROOT = "C:/tmp/YJH_monitoring_site_template";
const XLSX = path.join(ROOT, "inputs", "裕珍皇_案場輸入總表.xlsx");
const OUTPUT_JSON = path.join(ROOT, "outputs", "site_config_initial.json");
const GAP_REPORT = path.join(ROOT, "docs", "裕珍皇_缺漏清單.md");

const replacements = [
  ["R_3F_CHILLER", "R_3F_COLD_ROOM"],
  ["M_3F_CHILLER_A", "M_3F_COLD_ROOM_FREEZER_A"],
  ["C_3F_CHILLER_A", "C_3F_COLD_ROOM_FREEZER_A"],
  ["P_3F_CHILLER_A_CTRL_TEMP", "P_3F_COLD_ROOM_FREEZER_A_CTRL_TEMP"],
  ["A_M_3F_CHILLER_A_HIGH_TEMP", "A_M_3F_COLD_ROOM_FREEZER_A_HIGH_TEMP"],
  ["OBJ_R_3F_CHILLER", "OBJ_R_3F_COLD_ROOM"],
  ["V_3F_CHILLER_A_TEMP", "V_3F_COLD_ROOM_FREEZER_A_TEMP"],
  ["3F 冷藏庫 A 主機", "3F 冷藏庫 A 冷凍主機"],
  ["3F 冷藏庫 A 溫度卡", "3F 冷藏庫 A 冷凍主機溫度卡"],
];

function rectangular(values) {
  const max = Math.max(...values.map((row) => row.length));
  return values.map((row) => [...row, ...Array(max - row.length).fill("")]);
}

function normalize(value) {
  return String(value ?? "").trim();
}

function replaceValue(value) {
  if (typeof value !== "string") return value;
  let next = value;
  for (const [from, to] of replacements) {
    next = next.split(from).join(to);
  }
  return next;
}

function getSheetRows(workbook, sheetName) {
  const ws = workbook.worksheets.getItem(sheetName);
  const used = ws.getUsedRange(true);
  return rectangular(used.values);
}

function setWholeSheet(workbook, sheetName, rows) {
  const ws = workbook.worksheets.getItem(sheetName);
  const used = ws.getUsedRange(true);
  used.clear({ applyTo: "contents" });
  const next = rectangular(rows);
  ws.getRangeByIndexes(0, 0, next.length, next[0].length).values = next;
}

function replaceInSheet(workbook, sheetName) {
  const rows = getSheetRows(workbook, sheetName).map((row) => row.map(replaceValue));
  setWholeSheet(workbook, sheetName, rows);
}

function ensureMachineType(workbook) {
  const rows = getSheetRows(workbook, "03_主機");
  const headers = rows[0].map(normalize);
  const idIdx = headers.indexOf("machine_id");
  const typeIdx = headers.indexOf("machine_type");
  const nameIdx = headers.indexOf("machine_name");
  for (const row of rows.slice(1)) {
    if (normalize(row[idIdx]) === "M_3F_COLD_ROOM_FREEZER_A") {
      row[nameIdx] = "3F 冷藏庫 A";
      row[typeIdx] = "冷凍/冷藏主機待確認";
    }
  }
  setWholeSheet(workbook, "03_主機", rows);
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
    status: "initial_skeleton_cold_room_freezer_naming",
    naming_note: "庫房使用 COLD_ROOM，主機使用 FREEZER，避免 CHILLER 被誤解為冰水主機。",
    tables: extractTables(workbook),
  };
  await fs.writeFile(OUTPUT_JSON, JSON.stringify(payload, null, 2), "utf8");
}

async function writeGapReport() {
  const lines = [
    "# 裕珍皇案場缺漏清單",
    "",
    "## 命名規則",
    "",
    "- 庫房：使用 `COLD_ROOM`",
    "- 主機：使用 `FREEZER`",
    "- 不使用 `CHILLER`，避免誤解為冰水主機",
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
  const input = await FileBlob.load(XLSX);
  const workbook = await SpreadsheetFile.importXlsx(input);

  for (const sheet of workbook.worksheets.items) {
    replaceInSheet(workbook, sheet.name);
  }
  ensureMachineType(workbook);

  const scan = await workbook.inspect({
    kind: "match",
    searchTerm: "CHILLER|chiller",
    options: { useRegex: true, maxResults: 100 },
    summary: "chiller naming scan",
  });
  await fs.writeFile(path.join(ROOT, "docs", "chiller_naming_scan.ndjson"), scan.ndjson, "utf8");

  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(XLSX);
  await writeConfig(workbook);
  await writeGapReport();

  const tables = extractTables(workbook);
  console.log(JSON.stringify({
    rooms: tables["02_庫別"].length,
    machines: tables["03_主機"].length,
    controllers: tables["04_溫控器"].length,
    points: tables["08_點位表"].length,
    alarms: tables["10_告警"].length,
    coldRoomId: "R_3F_COLD_ROOM",
    freezerMachineId: "M_3F_COLD_ROOM_FREEZER_A",
  }, null, 2));
}

await main();
