/**
 * The designer's live preview (FORMS-11): `@aip/form-renderer` in editable mode on the unsaved
 * schema, with answers kept here only and the in-memory preview adapters (nothing is uploaded).
 * Desktop or Phone width (a 375 px frame). A schema the renderer cannot draw yet (mid-edit, with
 * lint issues) shows a message instead of breaking the page.
 */
import "@aip/form-renderer/styles.css";
import { FormRenderer, type Answers, type FormSchema } from "@aip/form-renderer";
import { Button, Panel } from "@aip/ui";
import { Component, useState, type ReactNode } from "react";
import { t } from "../../shell/t";
import { previewAdapters } from "../previewAdapters";

export const PHONE_WIDTH = 375;

class PreviewBoundary extends Component<{ children: ReactNode; schema: FormSchema }, { failed: boolean; schema: FormSchema }> {
  constructor(props: { children: ReactNode; schema: FormSchema }) {
    super(props);
    this.state = { failed: false, schema: props.schema };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  static getDerivedStateFromProps(props: { schema: FormSchema }, state: { failed: boolean; schema: FormSchema }) {
    // A new schema gets a fresh try.
    return props.schema !== state.schema ? { failed: false, schema: props.schema } : null;
  }

  render() {
    if (this.state.failed) {
      return (
        <p role="alert" className="dsg-preview__error">
          {t("forms.designer.preview.error")}
        </p>
      );
    }
    return this.props.children;
  }
}

export interface PreviewPaneProps {
  schema: FormSchema;
}

export function PreviewPane({ schema }: PreviewPaneProps) {
  const [adapters] = useState(previewAdapters);
  const [answers, setAnswers] = useState<Answers>({});
  const [width, setWidth] = useState<"desktop" | "phone">("desktop");
  // Remount the renderer on reset so its touched state clears too.
  const [round, setRound] = useState(0);

  const actions = (
    <>
      <div role="group" aria-label={t("forms.designer.preview.width")} className="dsg-switch">
        {(["desktop", "phone"] as const).map((w) => (
          <Button key={w} type="button" variant={width === w ? "primary" : "secondary"} aria-pressed={width === w} onClick={() => setWidth(w)}>
            {t(`forms.designer.preview.${w}`)}
          </Button>
        ))}
      </div>
      <Button
        type="button"
        variant="ghost"
        onClick={() => {
          setAnswers({});
          setRound((r) => r + 1);
        }}
      >
        {t("forms.designer.preview.reset")}
      </Button>
    </>
  );

  return (
    <Panel heading={t("forms.designer.preview.title")} actions={actions} className="dsg-preview">
      <div
        className={width === "phone" ? "dsg-preview__frame dsg-preview__frame--phone" : "dsg-preview__frame"}
        data-testid="designer-preview-frame"
        data-width={width}
        style={width === "phone" ? { width: PHONE_WIDTH, maxWidth: "100%" } : undefined}
      >
        <PreviewBoundary schema={schema}>
          <FormRenderer
            key={round}
            id="designer-preview"
            schema={schema}
            answers={answers}
            onChange={(next) => setAnswers(next)}
            // "submit" checks required fields too; errors still wait until a field is touched.
            mode="submit"
            t={t}
            adapters={adapters}
            showErrors="touched"
          />
        </PreviewBoundary>
      </div>
    </Panel>
  );
}
