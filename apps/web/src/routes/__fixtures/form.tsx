import "@aip/form-renderer/styles.css";
import {
  FormRenderer,
  type Answers,
  type FormSchema,
  type MediaAdapter,
  type ReferenceAdapter,
  type RendererAdapters,
} from "@aip/form-renderer";
import coating from "@aip/form-renderer/fixtures/coating-itr.json";
import { Button } from "@aip/ui";
import { useState } from "react";
import { t } from "../../features/shell/t";

/**
 * FORMS-03 dev-only fixture: renders the coating ITR fixture with in-memory stub adapters for the
 * Playwright journey and axe run (e2e/web/form-renderer.spec.ts). Loaded lazily by router.ts only
 * when `!import.meta.env.PROD`, so production bundles omit it. Fixture strings are test data, not
 * product labels; the renderer itself uses the app's `t` and `forms.renderer.*` keys.
 */

const schema = coating as FormSchema;

// Synthetic ids (valid UUIDs, so the evaluator accepts the stored answers).
const ASSETS = [
  { id: "00000000-0000-4000-8000-00000000a001", label: "PV-101 Pressure vessel" },
  { id: "00000000-0000-4000-8000-00000000a002", label: "TK-201 Storage tank" },
];
const USERS = [
  { id: "00000000-0000-4000-8000-00000000b001", label: "Alice Inspector" },
  { id: "00000000-0000-4000-8000-00000000b002", label: "Bob Painter" },
];

// A grey square, so photo thumbnails render without any network request.
const THUMBNAIL =
  "data:image/svg+xml;utf8," +
  encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#a3a3a3"/></svg>');

function stubAdapters(): RendererAdapters {
  let counter = 0;
  const media: MediaAdapter = {
    async pick(_fieldKey, kind) {
      counter += 1;
      const suffix = String(counter).padStart(12, "0");
      return {
        fileId: `00000000-0000-4000-8000-${suffix}`,
        name: kind === "photo" ? `photo-${counter}.jpg` : `signature-${counter}.png`,
      };
    },
    thumbnailUrl: () => THUMBNAIL,
  };
  const references: ReferenceAdapter = {
    async search(kind, query) {
      const q = query.trim().toLowerCase();
      return (kind === "asset" ? ASSETS : USERS).filter((item) => item.label.toLowerCase().includes(q));
    },
    async label(kind, id) {
      return (kind === "asset" ? ASSETS : USERS).find((item) => item.id === id)?.label ?? null;
    },
  };
  return { media, references };
}

export function FormFixture() {
  const [adapters] = useState(stubAdapters);
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
