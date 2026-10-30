/**
 * Start a new draft revision or replace the open draft's JSON (FORMS-04). New draft is
 * `POST /templates/{id}/revisions`: with empty JSON and a published revision, the server copies the
 * published schema. Replace is `PUT /revisions/{id}`. Lint issues (422 `TEMPLATE_INVALID`) are
 * listed and the text is kept; 409 (`DRAFT_EXISTS`, `REVISION_FROZEN`) closes with an error toast.
 */
import { useFormsRevisionsReplace, useFormsTemplatesAddRevision } from "@aip/api-client";
import { Button, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, FormField, Input, toast } from "@aip/ui";
import { useState } from "react";
import { t } from "../shell/t";
import { IssueList } from "./IssueList";
import { lintIssues, requestIssues, type Issue } from "./issues";
import { JsonInput } from "./JsonInput";
import { parseTemplateJson, type JsonError } from "./templateJson";

export type RevisionDialogMode =
  | { kind: "new"; templateId: string; code: string; canCopy: boolean }
  | { kind: "replace"; revisionId: string; revisionNo: number; initialText: string; initialNote: string };

export interface RevisionDialogProps {
  mode: RevisionDialogMode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** After a save (or a 409): the page refetches the template. */
  onSaved: (revisionNo: number | null) => void;
}

export function RevisionDialog({ mode, open, onOpenChange, onSaved }: RevisionDialogProps) {
  const add = useFormsTemplatesAddRevision();
  const replace = useFormsRevisionsReplace();
  const [json, setJson] = useState(mode.kind === "replace" ? mode.initialText : "");
  const [changeNote, setChangeNote] = useState(mode.kind === "replace" ? mode.initialNote : "");
  const [jsonError, setJsonError] = useState<JsonError | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const pending = add.isPending || replace.isPending;

  async function submit() {
    setIssues([]);
    setFormError(null);
    const copy = mode.kind === "new" && mode.canCopy && json.trim() === "";
    let schema: Record<string, unknown> | undefined;
    if (!copy) {
      const parsed = parseTemplateJson(json);
      if (!parsed.ok) {
        setJsonError(parsed.error);
        return;
      }
      schema = parsed.schema;
    }
    setJsonError(null);
    const note = changeNote.trim();

    const response =
      mode.kind === "new"
        ? await add.mutateAsync({
            templateId: mode.templateId,
            data: { ...(schema ? { schema } : {}), ...(note ? { changeNote: note } : {}) },
          })
        : await replace.mutateAsync({
            revisionId: mode.revisionId,
            data: { schema: schema ?? {}, ...(note ? { changeNote: note } : {}) },
          });

    if (response.status === 200 || response.status === 201) {
      const n = response.data.revisionNo;
      toast.success(mode.kind === "new" ? "forms.templates.draft.created" : "forms.templates.draft.saved", { n });
      onOpenChange(false);
      onSaved(n);
      return;
    }
    const body = response.data as unknown;
    const found = [...lintIssues(body), ...requestIssues(body)];
    if (found.length) {
      setIssues(found);
      return;
    }
    if ((response.status as number) === 409) {
      toast.error("forms.templates.error.conflict");
      onOpenChange(false);
      onSaved(null);
      return;
    }
    const id = response.headers.get("x-request-id");
    setFormError(
      (response.status as number) === 403
        ? t("forms.templates.error.forbidden")
        : id
          ? `${t("forms.templates.error.save")} ${t("forms.templates.error.request_id", { id })}`
          : t("forms.templates.error.save"),
    );
  }

  const title =
    mode.kind === "new"
      ? t("forms.templates.draft.new_title", { code: mode.code })
      : t("forms.templates.draft.replace_title", { n: mode.revisionNo });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("ui.close")} className="forms-dialog">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{t("forms.templates.draft.description")}</DialogDescription>
        <form
          className="forms-form"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <FormField label={t("forms.templates.field.change_note")}>
            {(control) => <Input {...control} value={changeNote} onChange={(e) => setChangeNote(e.target.value)} />}
          </FormField>
          <JsonInput
            value={json}
            onChange={setJson}
            error={jsonError}
            {...(mode.kind === "new" && mode.canCopy ? { hintKey: "forms.templates.draft.copy_hint" } : {})}
          />
          <IssueList issues={issues} />
          {formError ? (
            <p role="alert" className="aip-form-field__error">
              {formError}
            </p>
          ) : null}
          <div className="forms-form__actions">
            <Button type="submit" disabled={pending}>
              {pending ? t("forms.templates.draft.submitting") : t("forms.templates.draft.submit")}
            </Button>
            <DialogClose asChild>
              <Button type="button" variant="ghost">
                {t("forms.templates.form.cancel")}
              </Button>
            </DialogClose>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
