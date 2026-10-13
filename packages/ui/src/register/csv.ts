/**
 * `toCsv` (DESIGN-03): RFC 4180 CSV with a UTF-8 BOM, no DOM. Cells that a spreadsheet would run
 * as a formula (starting with `=`, `+`, `-`, `@`, tab or CR) get a leading `'`. The golden vectors
 * in `packages/contracts/csv-vectors/csv-v1.json` pin the output; the Python export endpoints run
 * the same file. Registers export through a server endpoint (`exportHref`), never from this
 * function on the client: it exists so both sides agree on the format.
 */
export interface CsvColumn {
  id: string;
  /** Header text; defaults to the id. */
  header?: string;
}

const BOM = "﻿";
const FORMULA_START = /^[=+\-@\t\r]/;
const NEEDS_QUOTES = /[",\r\n]/;

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function csvCell(value: unknown): string {
  let text = cellText(value);
  if (FORMULA_START.test(text)) text = `'${text}`;
  return NEEDS_QUOTES.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(columns: readonly CsvColumn[], rows: readonly Readonly<Record<string, unknown>>[]): string {
  const lines = [columns.map((c) => csvCell(c.header ?? c.id)).join(",")];
  for (const row of rows) lines.push(columns.map((c) => csvCell(row[c.id])).join(","));
  return BOM + lines.join("\r\n") + "\r\n";
}
