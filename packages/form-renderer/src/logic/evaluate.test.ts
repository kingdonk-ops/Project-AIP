// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { EVALUATOR_VERSION, evaluateAnswers } from "./evaluate";
import type { AnswerEvaluation, Answers, EvaluationContext, EvaluationMode, FormSchema, Json } from "./types";

interface EvaluateCase {
  name: string;
  schema: FormSchema;
  answers: Answers;
  mode: EvaluationMode;
  context: EvaluationContext | Record<string, Json> | null;
  expected: AnswerEvaluation;
}

function readVectors<T>(file: string): T {
  return JSON.parse(
    readFileSync(new URL(`../../../contracts/jsonlogic-vectors/forms/${file}`, import.meta.url), "utf8"),
  ) as T;
}

const vectors = readVectors<{ version: number; cases: EvaluateCase[] }>("evaluate-v1.json");
const vectorsV2 = readVectors<{
  version: number;
  cases: EvaluateCase[];
  v1Sections: Record<string, AnswerEvaluation["sections"]>;
}>("evaluate-v2.json");

describe("evaluate-v1 vectors", () => {
  it("the vector file is frozen at version 1 and meets the case floor", () => {
    expect(String(vectors.version)).toBe("1");
    expect(vectors.cases.length).toBeGreaterThanOrEqual(30);
  });

  // A v1 case is unchanged; FORMS-10's per-section result is checked against evaluate-v2.
  it.each(vectors.cases.map((c) => [c.name, c] as const))("%s", (name, c) => {
    const { sections, ...rest } = evaluateAnswers(c.schema, c.answers, { mode: c.mode, context: c.context });
    expect(rest).toEqual(c.expected);
    expect(sections).toEqual(vectorsV2.v1Sections[name]);
  });

  it("never mutates its answers argument", () => {
    const chain = vectors.cases.find((c) => c.name.startsWith("chain hides c"));
    expect(chain).toBeDefined();
    const answers = chain!.answers;
    const before = structuredClone(answers);
    evaluateAnswers(chain!.schema, answers, { mode: chain!.mode, context: chain!.context });
    expect(answers).toEqual(before);
  });
});

describe("evaluate-v2 vectors (FORMS-10 section rules)", () => {
  it("the vector file matches the evaluator version and covers every v1 case", () => {
    expect(String(vectorsV2.version)).toBe(EVALUATOR_VERSION);
    expect(vectorsV2.cases.length).toBeGreaterThanOrEqual(10);
    expect(Object.keys(vectorsV2.v1Sections).sort()).toEqual(vectors.cases.map((c) => c.name).sort());
  });

  it.each(vectorsV2.cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(evaluateAnswers(c.schema, c.answers, { mode: c.mode, context: c.context })).toEqual(
      c.expected,
    );
  });
});
