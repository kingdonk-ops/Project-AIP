/**
 * Add an item type to a content type (ITEMTYPES-03): its category, key, name, description and
 * the component flags. A new item type has no attributes yet; its schema is drafted and published
 * in the editor. A 409 `ITEM_TYPE_KEY_TAKEN` lands on the key field.
 */
import { schemas, type CategoryOut, type ItemTypeCreate } from "@aip/api-client";
import { Button, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, FormField, Input, toast } from "@aip/ui";
import { useState, type FormEvent } from "react";
import { t } from "../shell/t";
import { errorCode, requestId, useCreateItemType } from "./api";
import { CheckField } from "./ContentTypeDialog";

export interface ItemTypeDialogProps {
  open: boolean;
  categories: readonly CategoryOut[];
  onOpenChange: (open: boolean) => void;
}

export function ItemTypeDialog(props: ItemTypeDialogProps) {
  return props.open ? <ItemTypeDialogBody {...props} /> : null;
}

type Field = "categoryId" | "key" | "name";

function ItemTypeDialogBody({ open, categories, onOpenChange }: ItemTypeDialogProps) {
  const create = useCreateItemType();
  const [categoryId, setCategoryId] = useState(categories[0]?.id ?? "");
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isComponent, setIsComponent] = useState(false);
  const [allowsComponents, setAllowsComponents] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const body: ItemTypeCreate = {
      categoryId,
      key: key.trim(),
      name: name.trim(),
      description: description.trim() || null,
      isComponent,
      allowsComponents,
    };
    const parsed = schemas.ItemTypesItemTypesCreateBody.safeParse(body);
    const next: Partial<Record<Field, string>> = {};
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        if (issue.path[0] === "key") next.key = t("item_types.error.key");
        if (issue.path[0] === "name") next.name = t("item_types.error.name");
        if (issue.path[0] === "categoryId") next.categoryId = t("item_types.error.category");
      }
    }
    if (!categoryId) next.categoryId = t("item_types.error.category");
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    const response = await create.mutateAsync({ data: body });
    if (response.status === 201) {
      toast.success("item_types.item_type.created", { name: response.data.name });
      onOpenChange(false);
      return;
    }
    if (errorCode(response.data) === "ITEM_TYPE_KEY_TAKEN") {
      setErrors({ key: t("item_types.error.key_taken") });
      return;
    }
    const id = requestId(response);
    setFormError(id ? `${t("item_types.error.save")} ${t("item_types.error.request_id", { id })}` : t("item_types.error.save"));
  }

  const err = (field: Field) => (errors[field] ? { error: errors[field] } : {});

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("ui.close")}>
        <DialogTitle>{t("item_types.item_type.add")}</DialogTitle>
        <DialogDescription>{t("item_types.item_type.description")}</DialogDescription>
        <form className="item-types-form" noValidate onSubmit={(e) => void submit(e)}>
          <FormField label={t("item_types.item_type.field.category")} {...err("categoryId")}>
            {(control) => (
              <select {...control} className="item-types-select" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField label={t("item_types.item_type.field.key")} hint={t("item_types.field.key_hint")} {...err("key")}>
            {(control) => (
              <Input {...control} autoComplete="off" className="item-types-mono" value={key} onChange={(e) => setKey(e.target.value)} />
            )}
          </FormField>
          <FormField label={t("item_types.item_type.field.name")} {...err("name")}>
            {(control) => <Input {...control} value={name} onChange={(e) => setName(e.target.value)} />}
          </FormField>
          <FormField label={t("item_types.item_type.field.description")}>
            {(control) => <Input {...control} value={description} onChange={(e) => setDescription(e.target.value)} />}
          </FormField>
          <CheckField checked={isComponent} onChange={setIsComponent} label={t("item_types.item_type.field.is_component")} />
          <CheckField checked={allowsComponents} onChange={setAllowsComponents} label={t("item_types.item_type.field.allows_components")} />
          {formError ? (
            <p role="alert" className="aip-form-field__error">
              {formError}
            </p>
          ) : null}
          <div className="item-types-form__actions">
            <Button type="submit" disabled={create.isPending}>
              {t("item_types.item_type.add")}
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
