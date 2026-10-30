/**
 * Reading a form template from JSON text (FORMS-04). The text is either a revision schema
 * (`{"schemaVersion": 1, "sections": [...]}`) or an upload body (`{code, name, kind, changeNote,
 * schema}`), whose other keys pre-fill the upload dialog. This only parses: whether the template is
 * valid is the server's lint (`POST /forms/lint`), never a client copy of it.
 */

export const TEMPLATE_KINDS = ["inspection", "itp", "rfi", "permit", "test_report"] as const;
export type TemplateKind = (typeof TEMPLATE_KINDS)[number];

/** The biggest file the upload reads (the server refuses schemas over 256 KB). */
export const MAX_JSON_BYTES = 512 * 1024;

export type TemplateSchema = Record<string, unknown>;

export interface TemplateMeta {
  code?: string;
  name?: string;
  kind?: TemplateKind;
  changeNote?: string;
}

export interface JsonError {
  messageKey: string;
  line?: number;
  column?: number;
}

export type ParsedTemplate =
  | { ok: true; schema: TemplateSchema; meta: TemplateMeta }
  | { ok: false; error: JsonError };

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 1-based line and column of a character offset in `text`. */
export function lineColumn(text: string, position: number): { line: number; column: number } {
  const before = text.slice(0, Math.max(0, Math.min(position, text.length)));
  const lines = before.split("\n");
  return { line: lines.length, column: (lines[lines.length - 1]?.length ?? 0) + 1 };
}

/**
 * The offset of the first syntax error in `text`, or -1 when it is valid JSON. Engines word their
 * `JSON.parse` errors differently and V8 often names no position at all, so the page finds it itself.
 */
export function jsonErrorOffset(text: string): number {
  let i = 0;
  const ws = () => {
    while (i < text.length && " \t\n\r".includes(text[i]!)) i++;
  };
  const fail = (): never => {
    throw i;
  };
  const literal = (word: string) => {
    if (text.startsWith(word, i)) i += word.length;
    else fail();
  };
  const string = () => {
    i++; // opening quote
    while (i < text.length) {
      const c = text[i]!;
      if (c === '"') {
        i++;
        return;
      }
      if (c === "\\") {
        i++;
        if (text[i] === "u") {
          if (!/^[0-9a-fA-F]{4}$/.test(text.slice(i + 1, i + 5))) fail();
          i += 5;
        } else if (text[i] !== undefined && '"\\/bfnrt'.includes(text[i]!)) i++;
        else fail();
      } else if (c < " ") fail();
      else i++;
    }
    fail();
  };
  const number = () => {
    const match = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(i));
    if (!match || match[0] === "" || match[0] === "-") fail();
    i += match![0].length;
  };
  const value = (): void => {
    ws();
    const c = text[i];
    if (c === "{") {
      i++;
      ws();
      if (text[i] === "}") {
        i++;
        return;
      }
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
        else if (text[i] === "}") {
          i++;
          return;
        } else fail();
      }
    } else if (c === "[") {
      i++;
      ws();
      if (text[i] === "]") {
        i++;
        return;
      }
      for (;;) {
        value();
        ws();
        if (text[i] === ",") i++;
        else if (text[i] === "]") {
          i++;
          return;
        } else fail();
      }
    } else if (c === '"') string();
    else if (c === "t") literal("true");
    else if (c === "f") literal("false");
    else if (c === "n") literal("null");
    else if (c === "-" || (c !== undefined && c >= "0" && c <= "9")) number();
    else fail();
  };
  try {
    value();
    ws();
    if (i < text.length) fail();
    return -1;
  } catch (at) {
    return typeof at === "number" ? at : 0;
  }
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}

export function parseTemplateJson(source: string): ParsedTemplate {
  if (source.trim() === "") return { ok: false, error: { messageKey: "forms.templates.json.empty" } };
  let value: unknown;
  try {
    value = JSON.parse(source);
  } catch {
    const at = jsonErrorOffset(source);
    return {
      ok: false,
      error:
        at >= 0
          ? { messageKey: "forms.templates.json.parse_error", ...lineColumn(source, at) }
          : { messageKey: "forms.templates.json.parse_error_plain" },
    };
  }
  if (!isObject(value)) return { ok: false, error: { messageKey: "forms.templates.json.not_a_template" } };
  if ("sections" in value) return { ok: true, schema: value, meta: {} };
  if (!isObject(value.schema)) return { ok: false, error: { messageKey: "forms.templates.json.not_a_template" } };

  const meta: TemplateMeta = {};
  const code = text(value.code);
  const name = text(value.name);
  const changeNote = text(value.changeNote);
  if (code) meta.code = code;
  if (name) meta.name = name;
  if (typeof value.kind === "string" && (TEMPLATE_KINDS as readonly string[]).includes(value.kind)) {
    meta.kind = value.kind as TemplateKind;
  }
  if (changeNote) meta.changeNote = changeNote;
  return { ok: true, schema: value.schema, meta };
}
