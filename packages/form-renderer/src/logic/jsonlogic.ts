// A minimal, allow-listed JSONLogic evaluator: the TypeScript twin of the approvals transition
// guard (apps/api/aip/modules/approvals/guards/jsonlogic.py, ADR 0035 §1). It implements only the
// 17 allowed operators with jsonlogic.com semantics, refuses everything else, caps a guard at depth
// 20, 200 nodes and 8 KB serialised, and evaluates over deep-frozen facts. There is no
// `json-logic-js`: its global `add_operation` registry is exactly what the allow-list exists to
// avoid, so the operators live in a module-private Map that nothing outside this file can extend.

import type { Json } from "./types";

export const ALLOWED_OPERATORS: ReadonlySet<string> = new Set([
  "==",
  "!=",
  "===",
  "!==",
  "<",
  "<=",
  ">",
  ">=",
  "!",
  "!!",
  "and",
  "or",
  "if",
  "var",
  "missing",
  "missing_some",
  "in",
]);

const MAX_DEPTH = 20;
const MAX_NODES = 200;
const MAX_BYTES = 8 * 1024;

// The decimal numeric literals JavaScript's Number() accepts (hex/octal/binary omitted), matching
// the Python `_JS_NUMBER` regex exactly so coercion agrees across the two implementations.
const JS_NUMBER = /^[+-]?(?:Infinity|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)$/;

const ENCODER = new TextEncoder();

/** The guard is not allowed, or evaluating it failed. */
export class GuardError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GuardError";
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function operatorOf(node: Record<string, unknown>): string {
  const keys = Object.keys(node);
  if (keys.length !== 1) throw new GuardError("a guard operation has exactly one operator");
  return keys[0] as string;
}

function walk(node: unknown, depth: number, counter: { n: number }): void {
  if (depth > MAX_DEPTH) throw new GuardError("guard too deep");
  counter.n += 1;
  if (counter.n > MAX_NODES) throw new GuardError("guard too large");
  if (isObject(node)) {
    const op = operatorOf(node);
    if (!ALLOWED_OPERATORS.has(op)) throw new GuardError(`operator not allowed: ${op}`);
    walk(node[op], depth + 1, counter);
  } else if (Array.isArray(node)) {
    for (const item of node) walk(item, depth + 1, counter);
  } else if (!(node === null || ["string", "number", "boolean"].includes(typeof node))) {
    throw new GuardError(`not a JSON value: ${typeof node}`);
  }
}

/** Throw a GuardError unless `expr` is an allowed guard within the size limits. */
export function validateGuard(expr: unknown): void {
  if (!isObject(expr)) throw new GuardError("a guard is a JSONLogic operation (an object)");
  let size: number;
  try {
    size = ENCODER.encode(JSON.stringify(expr)).length;
  } catch {
    throw new GuardError("guard is not JSON");
  }
  if (size > MAX_BYTES) throw new GuardError("guard too large");
  walk(expr, 1, { n: 0 });
}

/** Deep-freeze a copy of `value`, leaving the input untouched (as Python's `_freeze` does). */
function freeze(value: unknown): unknown {
  if (Array.isArray(value)) return Object.freeze(value.map(freeze));
  if (isObject(value)) {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value)) out[key] = freeze(value[key]);
    return Object.freeze(out);
  }
  return value;
}

/** JSONLogic truthiness: like JavaScript (every object is true), except an empty array is false. */
export function truthy(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return true;
  if (typeof value === "number" && Number.isNaN(value)) return false;
  return Boolean(value);
}

/** JavaScript `Number(value)` for JSON values (NaN when it has none), matching Python `_number`. */
function toNumber(value: unknown): number {
  if (value === null || value === undefined) return 0;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const text = value.trim();
    if (!text) return 0;
    if (!JS_NUMBER.test(text)) return Number.NaN;
    return Number(text);
  }
  return Number.NaN;
}

function strictEqual(a: unknown, b: unknown): boolean {
  if (typeof a === "boolean" || typeof b === "boolean") {
    return typeof a === "boolean" && typeof b === "boolean" && a === b;
  }
  if (typeof a === "number" && typeof b === "number") return a === b;
  if (a === null || a === undefined || b === null || b === undefined) {
    return (a === null || a === undefined) && (b === null || b === undefined);
  }
  if (typeof a === "string" && typeof b === "string") return a === b;
  return a === b; // arrays and objects compare by identity, as in JavaScript
}

function looseEqual(a: unknown, b: unknown): boolean {
  if (a === null || a === undefined || b === null || b === undefined) {
    return (a === null || a === undefined) && (b === null || b === undefined);
  }
  if (typeof a === "object" || typeof b === "object") return a === b;
  if (typeof a === typeof b) return strictEqual(a, b);
  return toNumber(a) === toNumber(b); // number, string and boolean meet as numbers
}

function compare(a: unknown, b: unknown, op: (x: number | string, y: number | string) => boolean): boolean {
  if (typeof a === "string" && typeof b === "string") return op(a, b);
  const x = toNumber(a);
  const y = toNumber(b);
  if (Number.isNaN(x) || Number.isNaN(y)) return false;
  return op(x, y);
}

function less(args: unknown[], strict: boolean): boolean {
  const op = (x: number | string, y: number | string): boolean => (strict ? x < y : x <= y);
  if (args.length === 3) {
    return compare(args[0], args[1], op) && compare(args[1], args[2], op);
  }
  return compare(args[0], args[1], op);
}

function lookup(data: unknown, path: unknown, dflt: unknown = null): unknown {
  if (path === null || path === undefined || path === "" || (Array.isArray(path) && path.length === 0)) {
    return data;
  }
  let current: unknown = data;
  for (const part of String(path).split(".")) {
    if (isObject(current)) {
      if (!(part in current)) return dflt;
      current = current[part];
    } else if (Array.isArray(current) && /^[0-9]+$/.test(part)) {
      const index = Number(part);
      if (index >= current.length) return dflt;
      current = current[index];
    } else {
      return dflt;
    }
  }
  return current;
}

function missing(data: unknown, keys: unknown[]): unknown[] {
  return keys.filter((key) => {
    const value = lookup(data, key);
    return value === null || value === undefined || value === "";
  });
}

function argsOf(raw: unknown): unknown[] {
  return Array.isArray(raw) ? [...raw] : [raw];
}

function need(args: unknown[], n: number, op: string): void {
  if (args.length < n) throw new GuardError(`${op} needs ${n} arguments`);
}

type Operation = (data: unknown, args: unknown[]) => unknown;

const OPERATIONS = new Map<string, Operation>([
  ["==", (_d, a) => (need(a, 2, "=="), looseEqual(a[0], a[1]))],
  ["!=", (_d, a) => (need(a, 2, "!="), !looseEqual(a[0], a[1]))],
  ["===", (_d, a) => (need(a, 2, "==="), strictEqual(a[0], a[1]))],
  ["!==", (_d, a) => (need(a, 2, "!=="), !strictEqual(a[0], a[1]))],
  ["<", (_d, a) => (need(a, 2, "<"), less(a, true))],
  ["<=", (_d, a) => (need(a, 2, "<="), less(a, false))],
  [">", (_d, a) => (need(a, 2, ">"), compare(a[0], a[1], (x, y) => x > y))],
  [">=", (_d, a) => (need(a, 2, ">="), compare(a[0], a[1], (x, y) => x >= y))],
  ["!", (_d, a) => !truthy(a.length ? a[0] : null)],
  ["!!", (_d, a) => truthy(a.length ? a[0] : null)],
  ["var", (data, a) => lookup(data, a.length ? a[0] : null, a.length > 1 ? a[1] : null)],
  [
    "missing",
    (data, a) => missing(data, a.length === 1 && Array.isArray(a[0]) ? a[0] : a),
  ],
  [
    "missing_some",
    (data, a) => {
      need(a, 2, "missing_some");
      const minimum = a[0];
      const keys = a[1];
      if (typeof minimum !== "number" || !Number.isInteger(minimum) || !Array.isArray(keys)) {
        throw new GuardError("missing_some needs [minimum, [keys]]");
      }
      const absent = missing(data, keys);
      return keys.length - absent.length >= minimum ? [] : absent;
    },
  ],
  [
    "in",
    (_d, a) => {
      need(a, 2, "in");
      const [needle, haystack] = a;
      if (typeof haystack === "string") return typeof needle === "string" && haystack.includes(needle);
      if (Array.isArray(haystack)) return haystack.some((item) => strictEqual(needle, item));
      return false;
    },
  ],
]);

function apply(node: unknown, data: unknown): unknown {
  if (Array.isArray(node)) return node.map((item) => apply(item, data));
  if (!isObject(node)) return node;
  const op = operatorOf(node);
  if (!ALLOWED_OPERATORS.has(op)) throw new GuardError(`operator not allowed: ${op}`);
  const raw = argsOf(node[op]);

  // Lazy operators evaluate only the branches they need.
  if (op === "if") {
    let i = 0;
    while (i + 1 < raw.length) {
      if (truthy(apply(raw[i], data))) return apply(raw[i + 1], data);
      i += 2;
    }
    return i < raw.length ? apply(raw[i], data) : null;
  }
  if (op === "and" || op === "or") {
    if (raw.length === 0) throw new GuardError(`${op} needs at least one argument`);
    let value: unknown = null;
    for (const item of raw) {
      value = apply(item, data);
      if (truthy(value) === (op === "or")) return value;
    }
    return value;
  }

  const args = raw.map((item) => apply(item, data));
  const operation = OPERATIONS.get(op);
  if (operation === undefined) throw new GuardError(`operator not allowed: ${op}`);
  return operation(data, args);
}

/** The guard's value for `data` (read-only). Throws a GuardError on any failure. */
export function evaluateGuard(expr: Json, data: Record<string, Json>): unknown {
  validateGuard(expr);
  const frozen = freeze(data);
  try {
    return apply(expr, frozen);
  } catch (error) {
    if (error instanceof GuardError) throw error;
    const name = error instanceof Error ? error.constructor.name : "Error";
    throw new GuardError(`guard evaluation failed: ${name}`);
  }
}
