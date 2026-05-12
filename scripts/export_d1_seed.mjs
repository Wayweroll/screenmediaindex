#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const csvPath = path.join(root, "outputs", "reading_index.csv");
const outPath = path.join(root, "outputs", "d1_seed.sql");

const columns = [
  "row_key",
  "reading_id",
  "source_type",
  "source_title",
  "source_year",
  "source",
  "year",
  "magazine_title",
  "issue_date",
  "volume",
  "issue_number",
  "page_range",
  "publisher",
  "edition",
  "isbn",
  "book_title",
  "editor",
  "chapter_pages",
  "pdf_filename",
  "pdf_path",
  "file_location",
  "section",
  "title",
  "author",
  "printed_start_page",
  "pdf_page_number",
  "short_summary",
  "keywords",
  "specific_keywords",
  "people_films_discussed",
  "course_themes",
  "films_filmmakers_performers",
  "reading_type",
  "teaching_use",
  "notes",
  "confidence_note",
  "search_text",
];

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (quoted) {
      if (char === '"' && next === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char !== "\r") {
      field += char;
    }
  }

  if (field || row.length) {
    row.push(field);
    rows.push(row);
  }

  const [header, ...records] = rows;
  return records
    .filter((record) => record.some(Boolean))
    .map((record) =>
      Object.fromEntries(header.map((key, index) => [key, record[index] ?? ""])),
    );
}

function sqlValue(value, column) {
  if (value === undefined || value === null || value === "") return "NULL";
  if ((column === "year" || column === "source_year") && /^\d+$/.test(value)) {
    return value;
  }
  return `'${String(value).replaceAll("'", "''")}'`;
}

function normalizeSearch(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

const csvText = await fs.readFile(csvPath, "utf8");
const rows = parseCsv(csvText);
const statements = [
  "DELETE FROM readings;",
  ...rows.map((row, index) => {
    const seededRow = {
      ...row,
      row_key: `${row.reading_id || "reading"}-${String(index + 1).padStart(5, "0")}`,
    };
    seededRow.search_text = normalizeSearch([
      row.title,
      row.author,
      row.source_title,
      row.short_summary,
      row.keywords,
      row.specific_keywords,
      row.section,
      row.people_films_discussed,
      row.films_filmmakers_performers,
    ].join(" "));
    const values = columns.map((column) => sqlValue(seededRow[column], column)).join(", ");
    return `INSERT INTO readings (${columns.join(", ")}) VALUES (${values});`;
  }),
  "",
];

await fs.writeFile(outPath, statements.join("\n"), "utf8");
console.log(`Wrote ${rows.length} readings to ${outPath}`);
