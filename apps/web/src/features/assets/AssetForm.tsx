/**
 * Create and edit an asset (ASSETS-03). Name, Tag Number, parent (create only: moving is the move
 * dialog) and item type, then the attributes generated from the item-type version: the version the
 * asset is pinned to (edit), or the type's published version (create, or a changed type).
 *
 * The Tag Number is checked 300 ms after typing stops (`GET /assets?tagNumber=&limit=1`); the
 * server's 409 `TAG_NUMBER_IN_USE` stays authoritative and lands on the same field. A 422
 * `ATTRIBUTES_INVALID` puts each `errors[].path` on its attribute; a 409 `VERSION_CONFLICT` offers
 * a reload. "Save and add another" keeps the parent and item type and clears the rest.
 */
import {
  useAssetsCreate,
  useAssetsGet,
  useAssetsList,
  useAssetsUpdate,
  useItemTypesVersionsGet,
  type AssetDetail,
  type AssetOut,
} from "@aip/api-client";
import { Button, Combobox, ErrorState, FormField, Input, LoadingState, type RequestError } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { t } from "../shell/t";
import { AttributeFields, parseDefinitions, toAttributes, toRawValues, type RawValue, type RawValues } from "./AttributeFields";
import { invalidateAssets, useItemTypes } from "./data";
import { ParentPicker } from "./ParentPicker";
import { errorCode, errorMessage, withReference } from "./terms";

export const TAG_CHECK_DELAY_MS = 300;
const MAX_NAME = 200;
const MAX_TAG = 64;
const VALIDATION_CODES: ReadonlySet<string> = new Set(["required", "type", "minimum", "maximum", "enum", "maxLength", "format"]);

export type AssetFormMode = { kind: "create"; parentId?: string | undefined } | { kind: "edit"; assetId: string };

export interface AssetFormProps {
  mode: AssetFormMode;
  permissions: readonly string[];
  /** After a create (not "save and add another"). */
  onCreated: (asset: AssetOut) => void;
  /** After an edit. */
  onSaved: (asset: AssetOut) => void;
}

/** Trim and collapse inner whitespace, as the server normalises a Tag Number. */
export function normaliseTag(value: string): string {
  return value.trim().split(/\s+/).filter(Boolean).join(" ");
}

function Denied({ messageKey }: { messageKey: string }) {
  return (
    <section className="assets-form" aria-labelledby="assets-denied">
      <h1 id="assets-denied">{t(messageKey)}</h1>
      <Link to="/assets">{t("assets.form.back")}</Link>
    </section>
  );
}

export function AssetForm(props: AssetFormProps) {
  if (props.mode.kind === "create") {
    if (!props.permissions.includes("asset.create")) return <Denied messageKey="assets.form.denied_create" />;
    return <AssetFormBody {...props} initial={null} parentId={props.mode.parentId} onReload={() => undefined} />;
  }
  if (!props.permissions.includes("asset.update")) return <Denied messageKey="assets.form.denied_update" />;
  return <EditLoader {...props} assetId={props.mode.assetId} />;
}

function EditLoader(props: AssetFormProps & { assetId: string }) {
  const query = useAssetsGet(props.assetId, { query: { retry: false } });
  const response = query.data;
  if (query.isPending || (query.isError && query.isFetching)) {
    return (
      <section className="assets-form" aria-busy="true">
        <LoadingState variant="spinner" translate={t} />
      </section>
    );
  }
  if (query.isError || response === undefined || response.status !== 200) {
    const error: RequestError = response ? { status: response.status, requestId: response.headers.get("x-request-id") } : {};
    return (
      <section className="assets-form">
        <ErrorState error={error} onRetry={() => void query.refetch()} translate={t} />
      </section>
    );
  }
  const asset = response.data;
  // Remount on a new version so a reload after a conflict starts from the server's values.
  return <AssetFormBody key={`${asset.id}:${asset.syncVersion}`} {...props} initial={asset} onReload={() => void query.refetch()} />;
}

type Errors = Readonly<Record<string, string>>;

interface BodyProps extends AssetFormProps {
  initial: AssetDetail | null;
  parentId?: string | undefined;
  onReload: () => void;
}

function AssetFormBody({ initial, parentId: initialParent, onCreated, onSaved, onReload }: BodyProps) {
  const editing = initial !== null;
  const queryClient = useQueryClient();
  const create = useAssetsCreate();
  const update = useAssetsUpdate();
  const itemTypes = useItemTypes();
  const nameRef = useRef<HTMLInputElement>(null);

  const [name, setName] = useState(initial?.name ?? "");
  const [tagNumber, setTagNumber] = useState(initial?.tagNumber ?? "");
  const [parentId, setParentId] = useState(initialParent ?? "");
  const [itemTypeId, setItemTypeId] = useState(initial?.itemTypeId ?? "");
  const [raw, setRaw] = useState<RawValues>({});
  const [errors, setErrors] = useState<Errors>({});
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [denied, setDenied] = useState(false);

  // The version whose attributes the form shows.
  const pinned = editing && itemTypeId === (initial.itemTypeId ?? "") ? initial.itemTypeVersionId : null;
  const chosen = itemTypes.items.find((i) => i.id === itemTypeId);
  const versionId = itemTypeId ? (pinned ?? chosen?.publishedVersionId ?? null) : null;
  const version = useItemTypesVersionsGet(itemTypeId, versionId ?? "", { query: { enabled: Boolean(itemTypeId && versionId) } });
  const definitions = useMemo(
    () => (version.data?.status === 200 ? parseDefinitions(version.data.data.attributes) : []),
    [version.data],
  );
  const versionReady = !itemTypeId || version.data?.status === 200;

  // Fill the inputs from the stored attributes once the pinned version's definitions arrive.
  const filled = useRef(false);
  useEffect(() => {
    if (filled.current || !initial || definitions.length === 0 || !pinned) return;
    filled.current = true;
    setRaw(toRawValues(definitions, initial.attributes as Record<string, unknown>));
  }, [definitions, initial, pinned]);

  // Live Tag Number check, 300 ms after typing stops.
  const [checkedTag, setCheckedTag] = useState(() => normaliseTag(tagNumber));
  useEffect(() => {
    const timer = setTimeout(() => setCheckedTag(normaliseTag(tagNumber)), TAG_CHECK_DELAY_MS);
    return () => clearTimeout(timer);
  }, [tagNumber]);
  const unchangedTag = editing && checkedTag.toUpperCase() === (initial.tagNumber ?? "").toUpperCase();
  const tagCheck = useAssetsList(
    { tagNumber: checkedTag, limit: 1 },
    { query: { enabled: checkedTag.length > 0 && checkedTag.length <= MAX_TAG && !unchangedTag } },
  );
  const holder = tagCheck.data?.status === 200 && checkedTag && !unchangedTag ? tagCheck.data.data.items[0] : undefined;
  const taken = holder && holder.id !== initial?.id ? holder : undefined;

  if (denied) return <Denied messageKey={editing ? "assets.form.denied_update" : "assets.form.denied_create"} />;

  const clearError = (field: string) =>
    setErrors((current) => {
      if (!(field in current) && !("form" in current)) return current;
      const rest = { ...current };
      delete rest[field];
      delete rest.form;
      return rest;
    });

  const tagError = errors.tagNumber ?? (taken ? t("assets.form.tag_number_taken", { name: taken.name, internalTag: taken.internalTag }) : undefined);

  const itemTypeOptions = [
    { value: "", label: t("assets.form.item_type_none") },
    ...itemTypes.published.map((i) => ({ value: i.id, label: i.name })),
    ...(initial?.itemTypeId && !itemTypes.published.some((i) => i.id === initial.itemTypeId)
      ? [{ value: initial.itemTypeId, label: itemTypes.names.get(initial.itemTypeId) ?? initial.itemTypeId }]
      : []),
  ];

  const attributeErrors: Record<string, string> = {};
  for (const [key, message] of Object.entries(errors)) {
    if (key.startsWith("attributes.")) attributeErrors[key.slice("attributes.".length)] = message;
  }

  function validate(): Errors {
    const found: Record<string, string> = {};
    const trimmed = name.trim();
    if (!trimmed || trimmed.length > MAX_NAME) found.name = t("assets.validation.name");
    if (normaliseTag(tagNumber).length > MAX_TAG) found.tagNumber = t("assets.validation.tag_number");
    return found;
  }

  function serverErrors(body: unknown, headers: Headers): Errors {
    const code = errorCode(body);
    const record = typeof body === "object" && body !== null ? (body as Record<string, unknown>) : {};
    if (code === "TAG_NUMBER_IN_USE") return { tagNumber: t("assets.error.TAG_NUMBER_IN_USE") };
    if (code === "ITEM_TYPE_NOT_PUBLISHED") return { itemTypeId: t("assets.error.ITEM_TYPE_NOT_PUBLISHED") };
    if (code === "PARENT_NOT_FOUND" || code === "ASSET_TREE_TOO_DEEP") {
      return editing ? { form: errorMessage(code) } : { parentId: errorMessage(code) };
    }
    if (code === "ATTRIBUTES_INVALID" && Array.isArray(record.errors)) {
      const found: Record<string, string> = { form: t("assets.error.ATTRIBUTES_INVALID") };
      for (const item of record.errors as unknown[]) {
        const e = typeof item === "object" && item !== null ? (item as { path?: unknown; code?: unknown }) : {};
        if (typeof e.path !== "string" || !e.path.startsWith("attributes.")) continue;
        const key = e.path.split(".").slice(0, 2).join(".");
        const which = typeof e.code === "string" && VALIDATION_CODES.has(e.code) ? e.code : "invalid";
        found[key] ??= t(`assets.validation.${which}`);
      }
      return found;
    }
    if (Array.isArray(record.detail)) {
      const found: Record<string, string> = {};
      for (const item of record.detail as { loc?: unknown }[]) {
        const loc = Array.isArray(item.loc) ? item.loc : [];
        if (loc[1] === "name") found.name = t("assets.validation.name");
        if (loc[1] === "tagNumber") found.tagNumber = t("assets.validation.tag_number");
      }
      if (Object.keys(found).length) return found;
    }
    return { form: withReference(errorMessage(code), headers) };
  }

  async function save(addAnother: boolean) {
    setNotice(null);
    const invalid = validate();
    if (Object.keys(invalid).length) {
      setErrors(invalid);
      return;
    }
    const tag = normaliseTag(tagNumber);
    const attributes = itemTypeId ? toAttributes(definitions, raw, (initial?.attributes as Record<string, unknown>) ?? {}) : undefined;
    setSaving(true);
    try {
      if (!editing) {
        const response = await create.mutateAsync({
          data: {
            name: name.trim(),
            tagNumber: tag || null,
            parentId: parentId || null,
            itemTypeId: itemTypeId || null,
            attributes: attributes ?? {},
          },
        });
        if (response.status === 201 || response.status === 200) {
          await invalidateAssets(queryClient);
          if (addAnother) {
            setName("");
            setTagNumber("");
            setRaw({});
            setErrors({});
            setNotice(t("assets.form.saved_another", { tag: response.data.internalTag }));
            nameRef.current?.focus();
          } else {
            onCreated(response.data);
          }
          return;
        }
        if ((response.status as number) === 403) return setDenied(true);
        setErrors(serverErrors(response.data as unknown, response.headers));
        return;
      }
      const typeChanged = itemTypeId !== (initial.itemTypeId ?? "");
      const response = await update.mutateAsync({
        assetId: initial.id,
        data: {
          syncVersion: initial.syncVersion,
          name: name.trim(),
          tagNumber: tag || null,
          ...(typeChanged ? { itemTypeId: itemTypeId || null } : {}),
          ...(attributes ? { attributes } : {}),
        },
      });
      if (response.status === 200) {
        await invalidateAssets(queryClient, initial.id);
        onSaved(response.data);
        return;
      }
      if ((response.status as number) === 403) return setDenied(true);
      if (response.status === 409 && errorCode(response.data as unknown) === "VERSION_CONFLICT") {
        setConflict(true);
        return;
      }
      setErrors(serverErrors(response.data as unknown, response.headers));
    } finally {
      setSaving(false);
    }
  }

  const errorProp = (field: string): { error?: string } => (errors[field] ? { error: errors[field] } : {});
  const titleId = editing ? "assets-edit-title" : "assets-create-title";

  return (
    <section className="assets-form" aria-labelledby={titleId}>
      <h1 id={titleId}>{editing ? t("assets.form.edit_title", { name: initial.name }) : t("assets.form.create_title")}</h1>
      {editing ? <p className="assets-form__internal-tag">{`${t("assets.field.internal_tag")}: ${initial.internalTag}`}</p> : null}
      {notice ? (
        <p role="status" className="assets-form__notice">
          {notice}
        </p>
      ) : null}
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void save(false);
        }}
      >
        <FormField label={t("assets.form.required_label", { label: t("assets.field.name") })} hint={t("assets.form.name_hint")} {...errorProp("name")}>
          {(control) => (
            <Input
              {...control}
              ref={nameRef}
              autoComplete="off"
              maxLength={MAX_NAME}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                clearError("name");
              }}
            />
          )}
        </FormField>
        <FormField label={t("assets.field.tag_number")} hint={t("assets.form.tag_number_hint")} {...(tagError ? { error: tagError } : {})}>
          {(control) => (
            <Input
              {...control}
              autoComplete="off"
              className="assets-form__mono"
              value={tagNumber}
              onChange={(e) => {
                setTagNumber(e.target.value);
                clearError("tagNumber");
              }}
            />
          )}
        </FormField>
        {editing ? null : (
          <FormField label={t("assets.field.parent")} hint={t("assets.form.parent_hint")} {...errorProp("parentId")}>
            {(control) => (
              <ParentPicker
                id={control.id}
                label={t("assets.field.parent")}
                value={parentId}
                onChange={(value) => {
                  setParentId(value);
                  clearError("parentId");
                }}
                topLevelLabel={t("assets.form.parent_none")}
                placeholder={t("assets.form.parent_search")}
              />
            )}
          </FormField>
        )}
        <FormField label={t("assets.field.item_type")} hint={t("assets.form.item_type_hint")} {...errorProp("itemTypeId")}>
          {(control) => (
            <Combobox
              id={control.id}
              aria-label={t("assets.field.item_type")}
              options={itemTypeOptions}
              value={itemTypeId}
              onValueChange={(value) => {
                setItemTypeId(value);
                setRaw({});
                clearError("itemTypeId");
              }}
            />
          )}
        </FormField>
        {editing && itemTypeId !== (initial.itemTypeId ?? "") && itemTypeId ? (
          <p role="status" className="assets-form__warning">
            {t("assets.form.item_type_changed")}
          </p>
        ) : null}

        {itemTypeId ? (
          <fieldset className="assets-form__attributes">
            <legend>{t("assets.form.attributes_title")}</legend>
            {versionReady ? (
              <AttributeFields
                definitions={definitions}
                values={raw}
                errors={attributeErrors}
                onChange={(key: string, value: RawValue) => {
                  setRaw((current) => ({ ...current, [key]: value }));
                  clearError(`attributes.${key}`);
                }}
              />
            ) : (
              <p className="assets-form__note">{t("assets.form.attributes_loading")}</p>
            )}
          </fieldset>
        ) : null}

        {conflict ? (
          <div role="alert" className="assets-form__conflict">
            <p>{t("assets.error.VERSION_CONFLICT")}</p>
            <Button variant="secondary" onClick={onReload}>
              {t("assets.form.reload")}
            </Button>
          </div>
        ) : null}
        {errors.form ? (
          <p role="alert" className="aip-form-field__error">
            {errors.form}
          </p>
        ) : null}
        <div className="assets-form__actions">
          <Button type="submit" disabled={saving || !versionReady}>
            {saving ? t("assets.form.saving") : t("assets.form.save")}
          </Button>
          {editing ? null : (
            <Button variant="secondary" disabled={saving || !versionReady} onClick={() => void save(true)}>
              {t("assets.form.save_and_add")}
            </Button>
          )}
          <Button variant="ghost" asChild>
            <Link to="/assets">{t("assets.form.cancel")}</Link>
          </Button>
        </div>
      </form>
    </section>
  );
}
