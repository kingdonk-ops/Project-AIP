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

const vectors = JSON.parse(
  readFileSync(
    new URL("../../../contracts/jsonlogic-vectors/forms/evaluate-v1.json", import.meta.url),
    "utf8",
  ),
) as { version: number; cases: EvaluateCase[] };

describe("evaluate-v1 vectors", () => {
  it("the vector file matches the evaluator version and the case floor", () => {
    expect(String(vectors.version)).toBe(EVALUATOR_VERSION);
    expect(vectors.cases.length).toBeGreaterThanOrEqual(30);
  });

  it.each(vectors.cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(evaluateAnswers(c.schema, c.answers, { mode: c.mode, context: c.context })).toEqual(
      c.expected,
    );
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
