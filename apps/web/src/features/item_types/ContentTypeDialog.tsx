/**
 * Create a content type (ITEMTYPES-03): key, name, icon (from the UI icon set) and whether it shows
 * in navigation. The body is checked with the Zod schema orval generates from the API, so the
 * Pydantic model stays the source of truth; a 409 `CONTENT_TYPE_KEY_TAKEN` lands on the key field.
 */
import { schemas, type ContentTypeCreate } from "@aip/api-client";
import { Button, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, FormField, iconNames, Input, Label, toast } from "@aip/ui";
import { useId, useState, type FormEvent } from "react";
import { t } from "../shell/t";
import { errorCode, requestId, useCreateContentType } from "./api";

type Field = "key" | "name" | "icon";
const FIELD_MESSAGE: Record<Field, string> = {
  key: "item_types.error.key",
  name: "item_types.error.name",
  icon: "item_types.error.icon",
};

/** A labelled checkbox (the forms on these pages share it). */
export function CheckField({ checked, onChange, label }: { checked: boolean; onChange: (checked: boolean) => void; label: string }) {
  const id = useId();
  return (
    <div className="item-types-check">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );
}

export interface ContentTypeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ContentTypeDialog({ open, onOpenChange }: ContentTypeDialogProps) {
  const create = useCreateContentType();
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("folder");
  const [showInNav, setShowInNav] = useState(true);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);

  function reset() {
    setKey("");
    setName("");
    setIcon("folder");
    setShowInNav(true);
    setErrors({});
    setFormError(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const body: ContentTypeCreate = { key: key.trim(), name: name.trim(), icon, showInNav };
    const parsed = schemas.ItemTypesContentTypesCreateBody.safeParse(body);
    if (!parsed.success) {
      const next: Partial<Record<Field, string>> = {};
      for (const issue of parsed.error.issues) {
        const field = issue.path[0];
        if (field === "key" || field === "name" || field === "icon") next[field] = t(FIELD_MESSAGE[field]);
      }
      setErrors(next);
      return;
    }
    setErrors({});
    const response = await create.mutateAsync({ data: body });
    if (response.status === 201) {
      toast.success("item_types.content_type.created", { name: response.data.name });
      reset();
      onOpenChange(false);
      return;
    }
    if (errorCode(response.data) === "CONTENT_TYPE_KEY_TAKEN") {
      setErrors({ key: t("item_types.error.key_taken") });
      return;
    }
    const id = requestId(response);
    setFormError(id ? `${t("item_types.error.save")} ${t("item_types.error.request_id", { id })}` : t("item_types.error.save"));
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent closeLabel={t("ui.close")}>
        <DialogTitle>{t("item_types.content_type.create")}</DialogTitle>
        <DialogDescription>{t("item_types.content_type.create.description")}</DialogDescription>
        <form className="item-types-form" noValidate onSubmit={(e) => void submit(e)}>
          <FormField label={t("item_types.content_type.field.key")} hint={t("item_types.field.key_hint")} {...(errors.key ? { error: errors.key } : {})}>
            {(control) => (
              <Input {...control} autoComplete="off" className="item-types-mono" value={key} onChange={(e) => setKey(e.target.value)} />
            )}
          </FormField>
          <FormField label={t("item_types.content_type.field.name")} {...(errors.name ? { error: errors.name } : {})}>
            {(control) => <Input {...control} value={name} onChange={(e) => setName(e.target.value)} />}
          </FormField>
          <FormField label={t("item_types.content_type.field.icon")} {...(errors.icon ? { error: errors.icon } : {})}>
            {(control) => (
              <select {...control} className="item-types-select" value={icon} onChange={(e) => setIcon(e.target.value)}>
                {iconNames.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <CheckField checked={showInNav} onChange={setShowInNav} label={t("item_types.content_type.field.show_in_nav")} />
          {formError ? (
            <p role="alert" className="aip-form-field__error">
              {formError}
            </p>
          ) : null}
          <div className="item-types-form__actions">
            <Button type="submit" disabled={create.isPending}>
              {t("item_types.content_type.create.submit")}
            </Button>
            <DialogClose asChild>
              <Button type="button" variant="ghost">
                {t("item_types.action.cancel")}
              </Button>
            </DialogClose>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
