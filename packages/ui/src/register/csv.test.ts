// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { csvCell, toCsv, type CsvColumn } from "./csv";

interface Vector {
  name: string;
  columns: CsvColumn[];
  rows: Record<string, unknown>[];
  expected: string;
}

const vectors = JSON.parse(
  readFileSync(new URL("../../../contracts/csv-vectors/csv-v1.json", import.meta.url), "utf8"),
) as { cases: Vector[] };

describe("toCsv", () => {
  it("neutralises a formula payload and keeps RFC 4180 quoting", () => {
    const csv = toCsv([{ id: "name" }], [{ name: '=HYPERLINK("x")' }]);
    expect(csv).toContain(`"'=HYPERLINK(""x"")"`);
    expect(csv.startsWith("﻿")).toBe(true);
    expect(toCsv([{ id: "v" }], [{ v: "a,b\nc" }])).toContain('"a,b\nc"');
  });

  it.each(vectors.cases.map((c) => [c.name, c] as const))("golden vector: %s", (_name, vector) => {
    expect(toCsv(vector.columns, vector.rows)).toBe(vector.expected);
  });

  it("csvCell leaves plain text alone", () => {
    expect(csvCell("plain")).toBe("plain");
    expect(csvCell(undefined)).toBe("");
  });
});
