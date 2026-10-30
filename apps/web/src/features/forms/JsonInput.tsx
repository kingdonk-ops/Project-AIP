/**
 * The JSON input of the upload and draft dialogs (FORMS-04): a file picker whose text replaces a
 * monospace textarea (pasting works too), the parse error under it, and a Check button that asks
 * the server's lint (`POST /forms/lint`) without saving anything.
 */
import { useFormsLint } from "@aip/api-client";
import { Button, FormField } from "@aip/ui";
import { useState, type ChangeEvent } from "react";
import { t } from "../shell/t";
import { IssueList } from "./IssueList";
import { lintIssues, requestIssues, type Issue } from "./issues";
import { MAX_JSON_BYTES, parseTemplateJson, type JsonError } from "./templateJson";

export function jsonErrorText(error: JsonError): string {
  return error.line !== undefined && error.column !== undefined
    ? t(error.messageKey, { line: error.line, column: error.column })
    : t(error.messageKey);
}

export interface JsonInputProps {
  value: string;
  onChange: (text: string) => void;
  /** The parse error of the last submit, if any. */
  error?: JsonError | null;
  /** Extra hint under the textarea (e.g. "leave empty to copy"). */
  hintKey?: string;
}

type CheckState = { kind: "idle" } | { kind: "clean" } | { kind: "issues"; issues: Issue[] } | { kind: "failed" };

export function JsonInput({ value, onChange, error, hintKey }: JsonInputProps) {
  const lint = useFormsLint();
  const [fileError, setFileError] = useState<string | null>(null);
  const [checkError, setCheckError] = useState<JsonError | null>(null);
  const [check, setCheck] = useState<CheckState>({ kind: "idle" });

  const change = (text: string) => {
    setCheck({ kind: "idle" });
    setCheckError(null);
    onChange(text);
  };

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    setFileError(null);
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_JSON_BYTES) {
      setFileError(t("forms.templates.json.too_large"));
      return;
    }
    try {
      change(await file.text());
    } catch {
      setFileError(t("forms.templates.json.read_error"));
    }
  }

  async function runCheck() {
    setCheck({ kind: "idle" });
    const parsed = parseTemplateJson(value);
    if (!parsed.ok) {
      setCheckError(parsed.error);
      return;
    }
    setCheckError(null);
    const response = await lint.mutateAsync({ data: { schema: parsed.schema } });
    if (response.status === 200) {
      const issues = lintIssues(response.data);
      setCheck(issues.length ? { kind: "issues", issues } : { kind: "clean" });
      return;
    }
    const issues = requestIssues(response.data);
    setCheck(issues.length ? { kind: "issues", issues } : { kind: "failed" });
  }

  const shownError = checkError ?? error ?? null;
  const hint = [t("forms.templates.json.hint"), hintKey ? t(hintKey) : null].filter(Boolean).join(" ");

  return (
    <div className="forms-json">
      <FormField label={t("forms.templates.json.file")} {...(fileError ? { error: fileError } : {})}>
        {(control) => (
          <input {...control} type="file" accept="application/json,.json" onChange={(e) => void onFile(e)} />
        )}
      </FormField>
      <FormField
        label={t("forms.templates.json.label")}
        hint={hint}
        {...(shownError ? { error: jsonErrorText(shownError) } : {})}
      >
        {(control) => (
          <textarea
            {...control}
            className="aip-input forms-json__text forms-mono"
            rows={14}
            spellCheck={false}
            value={value}
            onChange={(e) => change(e.target.value)}
          />
        )}
      </FormField>
      <div className="forms-json__check">
        <Button type="button" variant="secondary" disabled={lint.isPending} onClick={() => void runCheck()}>
          {lint.isPending ? t("forms.templates.check.checking") : t("forms.templates.check.button")}
        </Button>
        <p role="status" className="forms-json__status">
          {check.kind === "clean" ? t("forms.templates.check.clean") : null}
          {check.kind === "failed" ? t("forms.templates.error.action") : null}
        </p>
      </div>
      {check.kind === "issues" ? <IssueList issues={check.issues} /> : null}
    </div>
  );
}
