#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const nodeModulesDir =
  process.env.NODE_MODULES_DIR || "/Users/nickocher/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const artifactPath = path.join(nodeModulesDir, "@oai", "artifact-tool", "dist", "artifact_tool.mjs");
const { SpreadsheetFile, Workbook } = await import(pathToFileURL(artifactPath));

const csvPath = path.join(root, "outputs", "reading_index.csv");
const outPath = path.join(root, "outputs", "reading_index.xlsx");
const csvText = await fs.readFile(csvPath, "utf8");

const workbook = await Workbook.fromCSV(csvText, { sheetName: "Reading Index" });
const sheet = workbook.worksheets.getItem("Reading Index");
const used = sheet.getUsedRange();
used.format.wrapText = true;
used.format.verticalAlignment = "Top";
sheet.freezePanes.freezeRows(1);

const header = sheet.getRange("A1:Q1");
header.format.fill.color = "#1F4E78";
header.format.font.color = "#FFFFFF";
header.format.font.bold = true;

const widths = {
  A: 120,
  B: 120,
  C: 70,
  D: 80,
  E: 240,
  F: 280,
  G: 140,
  H: 260,
  I: 160,
  J: 85,
  K: 85,
  L: 420,
  M: 240,
  N: 220,
  O: 240,
  P: 130,
  Q: 160,
};
for (const [col, width] of Object.entries(widths)) {
  sheet.getRange(`${col}:${col}`).format.columnWidthPx = width;
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outPath);
console.log(outPath);
