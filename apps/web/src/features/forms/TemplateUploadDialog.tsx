/**
 * Upload a form template as JSON (FORMS-04): code, name, kind, change note and the template JSON
 * (file or pasted). `POST /forms/templates` saves it as draft v1. The server's lint issues (422
 * `TEMPLATE_INVALID`) are listed under the JSON and the text is kept; 409 `CODE_TAKEN` and
 * request-validation errors land on their fields.
 */
import { getFormsTemplatesListQueryKey, useFormsTemplatesCreate, type TemplateCreateKind } from "@aip/api-client";
import { Button, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, FormField, Input, toast } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { t } from "../shell/t";
import { IssueList } from "./IssueList";
import { lintIssues, requestIssues, type Issue } from "./issues";
import { JsonInput } from "./JsonInput";
import { parseTemplateJson, TEMPLATE_KINDS, type JsonError, type TemplateKind } from "./templateJson";

const CODE_PATTERN = /^[a-z][a-z0-9-]{1,62}$/;

type FieldName = "code" | "name";

export interface TemplateUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (templateId: string) => void;
}

export function TemplateUploadDialog({ open, onOpenChange, onCreated }: TemplateUploadDialogProps) {
  const queryClient = useQueryClient();
  const create = useFormsTemplatesCreate();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState<TemplateKind>("inspection");
  const [kindChosen, setKindChosen] = useState(false);
  const [changeNote, setChangeNote] = useState("");
  const [json, setJson] = useState("");
  const [jsonError, setJsonError] = useState<JsonError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [issues, setIssues] = useState<Issue[]>([]);
  const [formError, setFormError] = useState<string | null>(null);

  function reset() {
    setCode("");
    setName("");
    setKind("inspection");
    setKindChosen(false);
    setChangeNote("");
    setJson("");
    setJsonError(null);
    setFieldErrors({});
    setIssues([]);
    setFormError(null);
  }

  async function submit() {
    setIssues([]);
    setFormError(null);
    const parsed = parseTemplateJson(json);
    if (!parsed.ok) {
      setJsonError(parsed.error);
      return;
    }
    setJsonError(null);
    // An upload body's code, name, kind and note fill the fields the user left empty.
    const values = {
      code: code.trim() || parsed.meta.code || "",
      name: name.trim() || parsed.meta.name || "",
      kind: !kindChosen && parsed.meta.kind ? parsed.meta.kind : kind,
      changeNote: changeNote.trim() || parsed.meta.changeNote || "",
    };
    setCode(values.code);
    setName(values.name);
    setKind(values.kind);
    setChangeNote(values.changeNote);

    const errors: Partial<Record<FieldName, string>> = {};
    if (!CODE_PATTERN.test(values.code)) errors.code = t("forms.templates.error.code");
    if (values.name === "" || values.name.length > 200) errors.name = t("forms.templates.error.name");
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    const response = await create.mutateAsync({
      data: {
        code: values.code,
        name: values.name,
        kind: values.kind as TemplateCreateKind,
        schema: parsed.schema,
        ...(values.changeNote ? { changeNote: values.changeNote } : {}),
      },
    });
    if (response.status === 201) {
      await queryClient.invalidateQueries({ queryKey: getFormsTemplatesListQueryKey().slice(0, 1) });
      toast.success("forms.templates.upload.created", { code: response.data.template.code });
      reset();
      onOpenChange(false);
      onCreated(response.data.template.id);
      return;
    }
    const body = response.data as unknown;
    const errorCode = (body as { code?: unknown } | null)?.code;
    if (response.status === 409 && errorCode === "CODE_TAKEN") {
      setFieldErrors({ code: t("forms.templates.error.code_taken") });
      return;
    }
    const lint = lintIssues(body);
    if (lint.length) {
      setIssues(lint);
      return;
    }
    const request = requestIssues(body);
    const onFields: Partial<Record<FieldName, string>> = {};
    for (const issue of request) {
      if (issue.path[0] === "code") onFields.code = t("forms.templates.error.code");
      if (issue.path[0] === "name") onFields.name = t("forms.templates.error.name");
    }
    setFieldErrors(onFields);
    const rest = request.filter((i) => i.path[0] !== "code" && i.path[0] !== "name");
    if (rest.length) setIssues(rest);
    if (request.length) return;
    const id = response.headers.get("x-request-id");
    setFormError(
      (response.status as number) === 403
        ? t("forms.templates.error.forbidden")
        : id
          ? `${t("forms.templates.error.save")} ${t("forms.templates.error.request_id", { id })}`
          : t("forms.templates.error.save"),
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("ui.close")} className="forms-dialog">
        <DialogTitle>{t("forms.templates.upload.title")}</DialogTitle>
        <DialogDescription>{t("forms.templates.upload.description")}</DialogDescription>
        <form
          className="forms-form"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <FormField
            label={t("forms.templates.field.code")}
            hint={t("forms.templates.field.code_hint")}
            {...(fieldErrors.code ? { error: fieldErrors.code } : {})}
          >
            {(control) => (
              <Input
                {...control}
                autoComplete="off"
                className="forms-mono"
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            )}
          </FormField>
          <FormField label={t("forms.templates.field.name")} {...(fieldErrors.name ? { error: fieldErrors.name } : {})}>
            {(control) => <Input {...control} value={name} onChange={(e) => setName(e.target.value)} />}
          </FormField>
          <FormField label={t("forms.templates.field.kind")}>
            {(control) => (
              <select
                {...control}
                className="aip-input forms-select"
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value as TemplateKind);
                  setKindChosen(true);
                }}
              >
                {TEMPLATE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`forms.kind.${k}`)}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField label={t("forms.templates.field.change_note")}>
            {(control) => <Input {...control} value={changeNote} onChange={(e) => setChangeNote(e.target.value)} />}
          </FormField>
          <JsonInput value={json} onChange={setJson} error={jsonError} />
          <IssueList issues={issues} />
          {formError ? (
            <p role="alert" className="aip-form-field__error">
              {formError}
            </p>
          ) : null}
          <div className="forms-form__actions">
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? t("forms.templates.upload.submitting") : t("forms.templates.upload.submit")}
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
