/**
 * Add or edit an item category of a content type (ITEMTYPES-03): key (fixed once created), name
 * and what it applies to (any, item or module, shown as terms). A 409 `CATEGORY_KEY_TAKEN` lands
 * on the key field; a stale edit (409 `VERSION_CONFLICT`) asks the user to reload.
 */
import { CategoryCreateApplicableFor, schemas, type CategoryCreate, type CategoryOut } from "@aip/api-client";
import { Button, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, FormField, Input, toast } from "@aip/ui";
import { useState, type FormEvent } from "react";
import { t } from "../shell/t";
import { errorCode, requestId, useCreateCategory, useUpdateCategory } from "./api";

export const APPLICABLE_FOR = Object.values(CategoryCreateApplicableFor);
type ApplicableFor = (typeof APPLICABLE_FOR)[number];

export interface CategoryDialogProps {
  open: boolean;
  contentTypeId: string;
  /** Undefined adds a category; a category edits it. */
  category?: CategoryOut | undefined;
  onOpenChange: (open: boolean) => void;
}

export function CategoryDialog(props: CategoryDialogProps) {
  // Keyed so each opening starts from the category's current values.
  return props.open ? <CategoryDialogBody key={props.category?.id ?? "new"} {...props} /> : null;
}

function CategoryDialogBody({ open, contentTypeId, category, onOpenChange }: CategoryDialogProps) {
  const editing = category !== undefined;
  const create = useCreateCategory();
  const update = useUpdateCategory();
  const [key, setKey] = useState(category?.key ?? "");
  const [name, setName] = useState(category?.name ?? "");
  const [applicableFor, setApplicableFor] = useState<ApplicableFor>(category?.applicableFor ?? "any");
  const [errors, setErrors] = useState<{ key?: string; name?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const next: { key?: string; name?: string } = {};
    if (!editing) {
      const body: CategoryCreate = { contentTypeId, key: key.trim(), name: name.trim(), applicableFor };
      const parsed = schemas.ItemTypesCategoriesCreateBody.safeParse(body);
      if (!parsed.success) {
        for (const issue of parsed.error.issues) {
          if (issue.path[0] === "key") next.key = t("item_types.error.key");
          if (issue.path[0] === "name") next.name = t("item_types.error.name");
        }
      }
    } else if (!name.trim()) next.name = t("item_types.error.name");
    setErrors(next);
    if (next.key || next.name) return;

    const response = editing
      ? await update.mutateAsync({
          categoryId: category.id,
          data: { syncVersion: category.syncVersion, name: name.trim(), applicableFor },
        })
      : await create.mutateAsync({ data: { contentTypeId, key: key.trim(), name: name.trim(), applicableFor } });
    if (response.status === 200 || response.status === 201) {
      toast.success(editing ? "item_types.category.saved" : "item_types.category.created", { name: name.trim() });
      onOpenChange(false);
      return;
    }
    const code = errorCode(response.data);
    if (code === "CATEGORY_KEY_TAKEN") {
      setErrors({ key: t("item_types.error.key_taken") });
      return;
    }
    if (code === "VERSION_CONFLICT") {
      setFormError(t("item_types.error.conflict"));
      return;
    }
    const id = requestId(response);
    setFormError(id ? `${t("item_types.error.save")} ${t("item_types.error.request_id", { id })}` : t("item_types.error.save"));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("ui.close")}>
        <DialogTitle>{t(editing ? "item_types.category.edit" : "item_types.category.add")}</DialogTitle>
        <DialogDescription>{t("item_types.category.description")}</DialogDescription>
        <form className="item-types-form" noValidate onSubmit={(e) => void submit(e)}>
          {editing ? null : (
            <FormField label={t("item_types.category.field.key")} hint={t("item_types.field.key_hint")} {...(errors.key ? { error: errors.key } : {})}>
              {(control) => (
                <Input {...control} autoComplete="off" className="item-types-mono" value={key} onChange={(e) => setKey(e.target.value)} />
              )}
            </FormField>
          )}
          <FormField label={t("item_types.category.field.name")} {...(errors.name ? { error: errors.name } : {})}>
            {(control) => <Input {...control} value={name} onChange={(e) => setName(e.target.value)} />}
          </FormField>
          <FormField label={t("item_types.category.field.applicable_for")}>
            {(control) => (
              <select
                {...control}
                className="item-types-select"
                value={applicableFor}
                onChange={(e) => setApplicableFor(e.target.value as ApplicableFor)}
              >
                {APPLICABLE_FOR.map((value) => (
                  <option key={value} value={value}>
                    {t(`item_types.applicable_for.${value}`)}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          {formError ? (
            <p role="alert" className="aip-form-field__error">
              {formError}
            </p>
          ) : null}
          <div className="item-types-form__actions">
            <Button type="submit" disabled={create.isPending || update.isPending}>
              {t(editing ? "item_types.action.save" : "item_types.category.add")}
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
