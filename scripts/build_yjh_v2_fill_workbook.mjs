import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "..");
const configPath = path.join(rootDir, "outputs", "site_config_initial.json");
const outputDir = path.join(rootDir, "outputs", "v2_fill_forms");
const outputPath = path.join(outputDir, "裕珍皇_案場資料回填表_V2.xlsx");

const config = JSON.parse(await fs.readFile(configPath, "utf8"));
const tables = config.tables;

const workbook = Workbook.create();

const colors = {
  title: "#0F4C5C",
  header: "#1F6F78",
  header2: "#2F855A",
  note: "#FFF7D6",
  editable: "#FFFFFF",
  required: "#FFF1F2",
  locked: "#F3F4F6",
  border: "#CBD5E1",
  text: "#111827",
};

function writeTable(sheet, startCell, headers, rows, options = {}) {
  const start = parseA1(startCell);
  const matrix = [headers, ...rows];
  const range = sheet.getRangeByIndexes(start.row, start.col, matrix.length, headers.length);
  range.values = matrix;
  const headerRange = sheet.getRangeByIndexes(start.row, start.col, 1, headers.length);
  headerRange.format = {
    fill: options.headerFill ?? colors.header,
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: colors.border },
  };
  const bodyRange = sheet.getRangeByIndexes(start.row + 1, start.col, rows.length, headers.length);
  bodyRange.format = {
    fill: options.bodyFill ?? colors.editable,
    font: { color: colors.text },
    wrapText: true,
    verticalAlignment: "top",
    borders: {
      insideHorizontal: { style: "thin", color: "#E5E7EB" },
      insideVertical: { style: "thin", color: "#E5E7EB" },
      bottom: { style: "thin", color: colors.border },
      left: { style: "thin", color: colors.border },
      right: { style: "thin", color: colors.border },
    },
  };
  sheet.tables.add(
    range.address,
    true,
    options.tableName ?? `Table_${sheet.name.replace(/\W/g, "_")}_${start.row + 1}`,
  );
  return range;
}

function parseA1(a1) {
  const match = /^([A-Z]+)(\d+)$/i.exec(a1);
  if (!match) throw new Error(`Invalid A1: ${a1}`);
  const letters = match[1].toUpperCase();
  let col = 0;
  for (const ch of letters) col = col * 26 + (ch.charCodeAt(0) - 64);
  return { row: Number(match[2]) - 1, col: col - 1 };
}

function setTitle(sheet, title, subtitle = "") {
  sheet.showGridLines = false;
  sheet.getRange("A1:H1").merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = {
    fill: colors.title,
    font: { bold: true, color: "#FFFFFF", size: 16 },
    verticalAlignment: "center",
  };
  sheet.getRange("A1").format.rowHeightPx = 34;
  if (subtitle) {
    sheet.getRange("A2:H2").merge();
    sheet.getRange("A2").values = [[subtitle]];
    sheet.getRange("A2").format = {
      fill: colors.note,
      font: { color: "#713F12" },
      wrapText: true,
      verticalAlignment: "center",
    };
    sheet.getRange("A2").format.rowHeightPx = 38;
  }
}

function fit(sheet, colWidths) {
  for (const [col, width] of Object.entries(colWidths)) {
    sheet.getRange(`${col}:${col}`).format.columnWidth = width;
  }
}

function pending(value) {
  return value === undefined || value === null || value === "" ? "待確認" : value;
}

function roomById(id) {
  return tables["02_庫別"].find((room) => room.room_id === id);
}

function controllerById(id) {
  return tables["04_溫控器"].find((controller) => controller.controller_id === id);
}

function pointByMachine(id) {
  return tables["08_點位表"].find((point) => point.machine_id === id);
}

function makeSummarySheet() {
  const sheet = workbook.worksheets.add("00_總覽");
  setTitle(sheet, "裕珍皇案場資料回填表 V2", "用途：給工程/現場/客戶逐項補齊缺漏資料；粉紅底欄位為優先必填。");
  const rows = [
    ["案場名稱", config.site_name, "site_id", config.site_id],
    ["客戶名稱", tables["01_案場"][0].customer_name, "時區", tables["01_案場"][0].timezone],
    ["案場地址", tables["01_案場"][0].address, "產出時間", new Date().toISOString().slice(0, 19)],
    ["庫別數", tables["02_庫別"].length, "主機數", tables["03_主機"].length],
    ["IoT627", tables["04_溫控器"].length, "數位電表", tables["06_電表"].length],
  ];
  writeTable(sheet, "A4", ["項目", "內容", "項目", "內容"], rows, {
    tableName: "SummaryTable",
    headerFill: colors.header2,
  });

  const todo = [
    ["P0", "IoT627", "型號、RS485 站號、baud/parity/stop bit、register table"],
    ["P0", "庫別", "每個庫別目標溫度上下限與高溫告警門檻"],
    ["P0", "電表", "品牌型號、相別、CT/PT、站號、通訊參數、量測項目"],
    ["P1", "Gateway/MQTT", "型號、MAC、IP、host/port/TLS/topic"],
    ["P1", "平面圖", "1F/3F 庫別、設備、座標與物件尺寸"],
    ["P2", "額外偵測器", "門磁、溫濕度、壓力、電流、漏水等是否需要"],
  ];
  writeTable(sheet, "A12", ["優先", "類別", "要補內容"], todo, {
    tableName: "PriorityTodoTable",
    headerFill: "#B45309",
  });
  fit(sheet, { A: 14, B: 28, C: 18, D: 36, E: 16, F: 16, G: 16, H: 16 });
  sheet.freezePanes.freezeRows(3);
}

function makeRoomsSheet() {
  const sheet = workbook.worksheets.add("01_庫別溫度");
  setTitle(sheet, "庫別目標溫度回填", "請先補 target_temp_low_c / target_temp_high_c；告警門檻可先用高溫上限再加安全差值。");
  const rows = tables["02_庫別"].map((room) => [
    room.room_id,
    room.room_name,
    room.room_type,
    room.machine_count,
    room.target_temp_low_c,
    room.target_temp_high_c,
    "待確認",
    "待確認",
    room.remarks,
  ]);
  writeTable(
    sheet,
    "A4",
    ["room_id", "庫別名稱", "庫別類型", "主機數", "目標低溫 C", "目標高溫 C", "高溫告警 C", "延遲秒數", "備註"],
    rows,
    { tableName: "RoomTemperatureFillTable" },
  );
  sheet.getRange("E5:H10").format.fill = colors.required;
  fit(sheet, { A: 24, B: 18, C: 18, D: 10, E: 14, F: 14, G: 14, H: 12, I: 40 });
  sheet.freezePanes.freezeRows(4);
}

function makeControllersSheet() {
  const sheet = workbook.worksheets.add("02_IoT627通訊");
  setTitle(sheet, "IoT627 溫控器通訊資料回填", "每台主機各一台 IoT627；站號不可重複，通訊參數需與 Gateway 串口一致。");
  const rows = tables["03_主機"].map((machine) => {
    const controller = controllerById(machine.controller_id);
    return [
      controller.controller_id,
      machine.machine_id,
      machine.machine_name,
      pending(controller.model),
      pending(controller.slave_id),
      pending(controller.baud_rate),
      pending(controller.parity),
      pending(controller.data_bits),
      pending(controller.stop_bits),
      pending(controller.supports_write),
      pending(controller.register_table_ref),
      "待確認",
    ];
  });
  writeTable(
    sheet,
    "A4",
    ["controller_id", "machine_id", "主機名稱", "完整型號", "RS485站號", "baud", "parity", "data_bits", "stop_bits", "是否允許寫入", "點位表來源", "現場備註"],
    rows,
    { tableName: "IoT627CommunicationFillTable" },
  );
  sheet.getRange("D5:K16").format.fill = colors.required;
  fit(sheet, { A: 30, B: 32, C: 20, D: 18, E: 12, F: 12, G: 12, H: 10, I: 10, J: 14, K: 24, L: 28 });
  sheet.freezePanes.freezeRows(4);
}

function makeMachinesSheet() {
  const sheet = workbook.worksheets.add("03_主機規格");
  setTitle(sheet, "主機設備規格回填", "主機命名採 FREEZER，不使用 CHILLER；品牌/型號/HP/冷媒會影響後續報表與維護資訊。");
  const rows = tables["03_主機"].map((machine) => [
    machine.machine_id,
    roomById(machine.room_id).room_name,
    machine.machine_name,
    machine.machine_type,
    machine.brand,
    machine.model,
    machine.compressor_hp,
    machine.refrigerant,
    machine.controller_id,
    "待確認",
    machine.remarks,
  ]);
  writeTable(
    sheet,
    "A4",
    ["machine_id", "庫別", "主機名稱", "主機類型", "品牌", "型號", "HP", "冷媒", "controller_id", "配電盤/迴路", "備註"],
    rows,
    { tableName: "MachineSpecFillTable" },
  );
  sheet.getRange("D5:H16").format.fill = colors.required;
  fit(sheet, { A: 34, B: 18, C: 22, D: 20, E: 16, F: 18, G: 10, H: 12, I: 30, J: 18, K: 28 });
  sheet.freezePanes.freezeRows(4);
}

function makeMetersSheet() {
  const sheet = workbook.worksheets.add("04_電表");
  setTitle(sheet, "數位電表資料回填", "目前骨架有 1F CP-1 與 3F CP-3；請確認是否為同一串 RS485 或分串。");
  const rows = tables["06_電表"].map((meter) => [
    meter.meter_id,
    meter.remarks.replace("數位電表：", "").split("，")[0],
    meter.brand,
    meter.model,
    meter.phase_type,
    meter.slave_id,
    meter.baud_rate,
    "待確認",
    "待確認",
    meter.ct_ratio,
    meter.pt_ratio,
    meter.points_required,
    "待確認",
  ]);
  writeTable(
    sheet,
    "A4",
    ["meter_id", "盤名", "品牌", "型號", "相別", "站號", "baud", "parity", "stop_bits", "CT", "PT", "量測項目", "備註"],
    rows,
    { tableName: "PowerMeterFillTable" },
  );
  sheet.getRange("C5:L6").format.fill = colors.required;
  fit(sheet, { A: 20, B: 14, C: 16, D: 18, E: 12, F: 10, G: 10, H: 10, I: 10, J: 12, K: 12, L: 30, M: 26 });
  sheet.freezePanes.freezeRows(4);
}

function makeGatewaySheet() {
  const sheet = workbook.worksheets.add("05_Gateway_MQTT");
  setTitle(sheet, "Gateway / MQTT 資料回填", "topic、TLS、client_id 與帳密需和平台端設定一致；密碼只填保管位置，不建議明碼寫入。");
  const gw = tables["07_Gateway_MQTT"][0];
  const rows = [
    ["gateway_id", gw.gateway_id, "固定"],
    ["gateway_type", gw.gateway_type, "Gateway 型號/廠牌"],
    ["mac_address", gw.mac_address, "設備 MAC"],
    ["gw_id", gw.gw_id, "平台識別用 Gateway ID"],
    ["local_ip", gw.local_ip, "現場區網 IP"],
    ["mqtt_host", gw.mqtt_host, "MQTT broker host"],
    ["mqtt_port", gw.mqtt_port, "8801/8883 依平台確認"],
    ["tls_enabled", gw.tls_enabled, "Y/N"],
    ["tls_version", gw.tls_version, "例如 TLSV1_2"],
    ["client_id", gw.client_id, "預設可用"],
    ["publish_topics", gw.publish_topics, "上拋 topic"],
    ["subscribe_topics", gw.subscribe_topics, "命令 topic"],
    ["username", gw.username, "若需要"],
    ["password_ref", gw.password_ref, "密碼保管位置/引用名稱"],
  ];
  writeTable(sheet, "A4", ["欄位", "回填值", "說明"], rows, {
    tableName: "GatewayMqttFillTable",
  });
  sheet.getRange("B5:B18").format.fill = colors.required;
  fit(sheet, { A: 22, B: 34, C: 54, D: 16, E: 16, F: 16, G: 16, H: 16 });
  sheet.freezePanes.freezeRows(4);
}

function makePointsSheet() {
  const sheet = workbook.worksheets.add("06_點位與告警");
  setTitle(sheet, "控制溫度點位與高溫告警回填", "目前每台主機先建一個控制溫度與一個高溫告警；Modbus/MQTT 欄位待點位表確認。");
  const alarms = tables["10_告警"];
  const rows = tables["03_主機"].map((machine) => {
    const point = pointByMachine(machine.machine_id);
    const alarm = alarms.find((item) => item.point_id === point.point_id);
    return [
      point.point_id,
      machine.machine_name,
      point.device_id,
      point.point_name,
      point.modbus_address,
      point.data_type,
      point.scale,
      point.unit,
      point.normal_min,
      point.normal_max,
      alarm.alarm_id,
      alarm.threshold,
      alarm.duration_sec,
      alarm.notify_group_id,
    ];
  });
  writeTable(
    sheet,
    "A4",
    ["point_id", "主機名稱", "device_id", "點位名稱", "modbus_address", "data_type", "scale", "unit", "normal_min", "normal_max", "alarm_id", "高溫門檻", "延遲秒數", "通知群組"],
    rows,
    { tableName: "PointAlarmFillTable" },
  );
  sheet.getRange("E5:M16").format.fill = colors.required;
  fit(sheet, { A: 38, B: 22, C: 30, D: 14, E: 18, F: 14, G: 12, H: 10, I: 12, J: 12, K: 38, L: 12, M: 12, N: 18 });
  sheet.freezePanes.freezeRows(4);
}

function makeFloorplanSheet() {
  const sheet = workbook.worksheets.add("07_平面圖座標");
  setTitle(sheet, "平面圖物件座標回填", "先補庫別區塊，後續可再加入主機、電表、Gateway、感測器等物件。");
  const rows = tables["12_平面圖"].map((item) => [
    item.floorplan_id,
    item.file_name,
    item.object_type,
    item.linked_id,
    roomById(item.linked_id)?.room_name ?? "",
    item.x,
    item.y,
    item.width,
    item.height,
    item.layer_name,
    item.remarks,
  ]);
  writeTable(
    sheet,
    "A4",
    ["floorplan_id", "檔名", "物件類型", "linked_id", "顯示名稱", "x", "y", "width", "height", "layer", "備註"],
    rows,
    { tableName: "FloorplanObjectFillTable" },
  );
  sheet.getRange("B5:I10").format.fill = colors.required;
  fit(sheet, { A: 14, B: 24, C: 12, D: 24, E: 18, F: 10, G: 10, H: 10, I: 10, J: 14, K: 32 });
  sheet.freezePanes.freezeRows(4);
}

function makeSensorsSheet() {
  const sheet = workbook.worksheets.add("08_額外偵測器");
  setTitle(sheet, "額外偵測器需求盤點", "若現場有門磁、溫濕度、壓力、電流、漏水等，請在此補新增需求。");
  const rows = tables["02_庫別"].map((room) => [
    room.room_id,
    room.room_name,
    "待確認",
    "待確認",
    "待確認",
    "待確認",
    "待確認",
    "",
  ]);
  writeTable(
    sheet,
    "A4",
    ["room_id", "庫別", "是否有門磁", "溫濕度", "壓力", "電流", "漏水", "其他/備註"],
    rows,
    { tableName: "ExtraSensorSurveyTable" },
  );
  sheet.getRange("C5:H10").format.fill = colors.required;
  fit(sheet, { A: 24, B: 18, C: 14, D: 14, E: 12, F: 12, G: 12, H: 36 });
  sheet.freezePanes.freezeRows(4);
}

makeSummarySheet();
makeRoomsSheet();
makeControllersSheet();
makeMachinesSheet();
makeMetersSheet();
makeGatewaySheet();
makePointsSheet();
makeFloorplanSheet();
makeSensorsSheet();

for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange();
  used.format.font = { name: "Microsoft JhengHei", size: 10, color: colors.text };
  used.format.verticalAlignment = "top";
}

await fs.mkdir(outputDir, { recursive: true });

const renders = [];
for (const sheet of workbook.worksheets.items) {
  const preview = await workbook.render({
    sheetName: sheet.name,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  const previewPath = path.join(outputDir, `${sheet.name}.png`);
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  renders.push(previewPath);
}

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

console.log(JSON.stringify({ outputPath, renders, formulaErrors: formulaErrors.ndjson }, null, 2));
