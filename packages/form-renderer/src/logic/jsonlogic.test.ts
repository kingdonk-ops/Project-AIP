import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import * as pkg from "../index";
import { ALLOWED_OPERATORS, evaluateGuard, GuardError, truthy, validateGuard } from "./jsonlogic";
import type { Json } from "./types";
import { EVALUATOR_VERSION } from "./evaluate";

interface ValueCase {
  name: string;
  expr: Json;
  data: Record<string, Json>;
  expected: unknown;
}
interface ErrorCase {
  name: string;
  expr: Json;
  error: string;
}
type Case = ValueCase | ErrorCase;

const vectors = JSON.parse(
  readFileSync(
    new URL("../../../contracts/jsonlogic-vectors/forms/expressions-v1.json", import.meta.url),
    "utf8",
  ),
) as { version: number; cases: Case[] };

const isError = (c: Case): c is ErrorCase => "error" in c;

describe("expressions-v1 vectors", () => {
  it("the vector file matches the evaluator version and the case floor", () => {
    expect(String(vectors.version)).toBe(EVALUATOR_VERSION);
    expect(vectors.cases.length).toBeGreaterThanOrEqual(80);
  });

  it.each(vectors.cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    if (isError(c)) {
      let thrown: unknown;
      try {
        evaluateGuard(c.expr, {});
      } catch (error) {
        thrown = error;
      }
      expect(thrown).toBeInstanceOf(GuardError);
      expect((thrown as GuardError).message).toBe(c.error);
    } else {
      expect(evaluateGuard(c.expr, c.data)).toEqual(c.expected);
    }
  });
});

describe("the allow-list cannot be widened", () => {
  it("exposes exactly the intended runtime exports and no operator registry", () => {
    expect(Object.keys(pkg).sort()).toEqual(
      ["ALLOWED_OPERATORS", "EVALUATOR_VERSION", "GuardError", "evaluateAnswers", "evaluateGuard", "truthy", "validateGuard"].sort(),
    );
  });

  it("rejects an operator outside the allow-list with the exact message", () => {
    expect(() => validateGuard({ some: [] })).toThrow(new GuardError("operator not allowed: some"));
  });

  it("has the 17 allowed operators and nothing else", () => {
    expect(ALLOWED_OPERATORS.size).toBe(17);
    expect(ALLOWED_OPERATORS.has("reduce")).toBe(false);
  });

  it("truthy follows JSONLogic (empty array false, object true, '0' true, 0 false)", () => {
    expect(truthy([])).toBe(false);
    expect(truthy({})).toBe(true);
    expect(truthy("0")).toBe(true);
    expect(truthy(0)).toBe(false);
  });
});
