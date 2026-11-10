import "@aip/form-renderer/styles.css";
import { FormRenderer, type Answers, type FormSchema } from "@aip/form-renderer";
import coating from "@aip/form-renderer/fixtures/coating-itr.json";
import { Button } from "@aip/ui";
import { useState } from "react";
import { previewAdapters } from "../../features/forms/previewAdapters";
import { t } from "../../features/shell/t";

/**
 * FORMS-03 dev-only fixture: renders the coating ITR fixture with in-memory stub adapters for the
 * Playwright journey and axe run (e2e/web/form-renderer.spec.ts). Loaded lazily by router.ts only
 * when `!import.meta.env.PROD`, so production bundles omit it. Fixture strings are test data, not
 * product labels; the renderer itself uses the app's `t` and `forms.renderer.*` keys.
 */

const schema = coating as FormSchema;

export function FormFixture() {
  const [adapters] = useState(previewAdapters);
  const [answers, setAnswers] = useState<Answers>({});
  const [submitted, setSubmitted] = useState(false);
  const [readOnly, setReadOnly] = useState(false);

  return (
    <main data-testid="form-fixture" style={{ maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <h1>{"Form renderer fixture"}</h1>
      <FormRenderer
        id="coating-itr"
        schema={schema}
        answers={answers}
        onChange={(next) => setAnswers(next)}
        mode={submitted ? "submit" : "draft"}
        context={{ kind: "inspection" }}
        t={t}
        adapters={adapters}
        readOnly={readOnly}
        showErrors={submitted ? "all" : "touched"}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <Button type="button" onClick={() => setSubmitted(true)}>
          {"Submit"}
        </Button>
        <Button type="button" variant="secondary" aria-pressed={readOnly} onClick={() => setReadOnly((v) => !v)}>
          {"Read-only"}
        </Button>
      </div>
    </main>
  );
}
