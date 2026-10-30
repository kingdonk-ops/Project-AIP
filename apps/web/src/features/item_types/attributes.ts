/**
 * Client-side checks of the attribute JSON (ITEMTYPES-03), run before any request. They are hints
 * only: the API's lint (ITEMTYPES-02, 422 `ATTRIBUTES_INVALID`) is the authority. A JSON syntax
 * error is reported with its 1-based line and column; once the text parses, each problem is a
 * hint `{key, index}` whose `key` is a terminology key.
 */
import { attributeFieldType, fieldType } from "./fieldTypes";

export type Attribute = Record<string, unknown>;

export interface AttributeHint {
  /** Terminology key (`item_types.hint.*`). */
  key: string;
  /** The attribute's position in the array, when the hint is about one attribute. */
  index?: number;
}

export interface ParseError {
  line: number;
  column: number;
}

export type ParseResult =
  | { ok: true; attributes: Attribute[]; hints: AttributeHint[] }
  | { ok: false; error: ParseError; hints: [] };

/** Line and column (1-based) of a 0-based offset in `text`. */
export function lineColumn(text: string, offset: number): ParseError {
  const before = text.slice(0, Math.max(0, Math.min(offset, text.length)));
  const lines = before.split("\n");
  return { line: lines.length, column: (lines.at(-1)?.length ?? 0) + 1 };
}

/**
 * The offset of the first JSON syntax error in `text` (a small recursive-descent scan), for when
 * the engine's message names no position (V8 omits it for some tokens; Safari always does).
 */
export function syntaxErrorOffset(text: string): number {
  let i = 0;
  const ws = () => {
    while (i < text.length && " \t\n\r".includes(text[i]!)) i++;
  };
  const fail = (): never => {
    throw i;
  };
  const literal = (word: string) => {
    for (const ch of word) {
      if (text[i] !== ch) fail();
      i++;
    }
  };
  const string = () => {
    i++; // opening quote
    while (i < text.length && text[i] !== '"') {
      if (text[i] === "\\") i++;
      else if (text.charCodeAt(i) < 0x20) fail();
      i++;
    }
    if (text[i] !== '"') fail();
    i++;
  };
  const number = () => {
    const match = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(i));
    if (!match) return fail();
    i += match[0].length;
  };
  const value = (): void => {
    ws();
    const ch = text[i];
    if (ch === "{") {
      i++;
      ws();
      if (text[i] === "}") return void i++;
      for (;;) {
        ws();
        if (text[i] !== '"') fail();
        string();
        ws();
        if (text[i] !== ":") fail();
        i++;
        value();
        ws();
        if (text[i] === ",") i++;
        else if (text[i] === "}") return void i++;
        else fail();
      }
    }
    if (ch === "[") {
      i++;
      ws();
      if (text[i] === "]") return void i++;
      for (;;) {
        value();
        ws();
        if (text[i] === ",") i++;
        else if (text[i] === "]") return void i++;
        else fail();
      }
    }
    if (ch === '"') return string();
    if (ch === "t") return literal("true");
    if (ch === "f") return literal("false");
    if (ch === "n") return literal("null");
    return number();
  };
  try {
    value();
    ws();
    if (i < text.length) fail();
  } catch (at) {
    if (typeof at === "number") return Math.min(at, text.length);
    throw at;
  }
  return text.length;
}

/** Where `JSON.parse` failed: from its message when it names a position, else by scanning. */
function errorPosition(text: string, error: unknown): ParseError {
  const message = error instanceof Error ? error.message : String(error);
  const lc = /line (\d+) column (\d+)/i.exec(message);
  if (lc) return { line: Number(lc[1]), column: Math.max(1, Number(lc[2])) };
  const position = /position (\d+)/i.exec(message);
  if (position) return lineColumn(text, Number(position[1]));
  return lineColumn(text, syntaxErrorOffset(text));
}

function isObject(value: unknown): value is Attribute {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseAttributes(text: string): ParseResult {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (error) {
    return { ok: false, error: errorPosition(text, error), hints: [] };
  }
  if (!Array.isArray(value)) {
    return { ok: true, attributes: [], hints: [{ key: "item_types.hint.not_an_array" }] };
  }
  const hints: AttributeHint[] = [];
  const attributes: Attribute[] = [];
  const keys = new Set<string>();
  value.forEach((item: unknown, index) => {
    if (!isObject(item)) {
      hints.push({ key: "item_types.hint.not_an_object", index });
      return;
    }
    attributes.push(item);
    const kind = item.fieldType;
    if (typeof kind !== "string" || fieldType(kind) === undefined) {
      hints.push({ key: "item_types.hint.field_type_unknown", index });
    } else if (attributeFieldType(kind) === undefined) {
      hints.push({ key: "item_types.hint.field_type_not_allowed", index });
    }
    if (typeof item.key === "string") {
      if (keys.has(item.key)) hints.push({ key: "item_types.hint.duplicate_key", index });
      keys.add(item.key);
    }
  });
  return { ok: true, attributes, hints };
}

/** Pretty-prints attributes the way the editor shows them (2 spaces). */
export function formatAttributes(attributes: readonly unknown[]): string {
  return JSON.stringify(attributes, null, 2);
}

/** The attribute index an API issue path (`attributes[3].config`) points at. */
export function issueIndex(path: string): number | undefined {
  const match = /^attributes\[(\d+)\]/.exec(path);
  return match ? Number(match[1]) : undefined;
}

/**
 * The offset in `text` where the top-level array's element `index` starts, so the editor can put
 * the caret on it. Strings are skipped, so brackets and commas inside values do not count.
 * Returns 0 when the text has no such element.
 */
export function elementOffset(text: string, index: number): number {
  let depth = 0;
  let inString = false;
  let escaped = false;
  let current = -1;
  let expecting = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]!;
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (expecting && !/\s/.test(ch)) {
      expecting = false;
      if (ch !== "]") {
        current += 1;
        if (current === index) return i;
      }
    }
    if (ch === '"') inString = true;
    else if (ch === "[" || ch === "{") {
      depth += 1;
      if (depth === 1 && ch === "[") expecting = true;
    } else if (ch === "]" || ch === "}") depth -= 1;
    else if (ch === "," && depth === 1) expecting = true;
  }
  return 0;
}
