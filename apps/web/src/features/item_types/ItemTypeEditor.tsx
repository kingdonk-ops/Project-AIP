/**
 * Item type editor `/admin/content-types/$contentTypeId/item-types/$itemTypeId` (ITEMTYPES-03) on
 * DESIGN-04's `RecordDetail`, tabs `details|schema|versions` in the URL. The header chip reads
 * "Published v{n}" or "Not published".
 *
 * - Details: the item-type definition form (name, description, component flags; key and category
 *   fixed), saved with `syncVersion`; a stale write shows the "changed by someone else" state.
 * - Schema: `AttributeJsonEditor` on the left (the draft's `attributes` as pretty-printed JSON) and
 *   `FieldPreview` on the right (of the current text when it parses, else of the last text that
 *   did, with the parse error above it); stacked below 768 px. Create draft copies the published
 *   version; Save draft sends the array; the server's 422 `ATTRIBUTES_INVALID` issues are listed
 *   under the editor and the text is kept. Discard asks first; Publish asks for a change summary.
 *   Without a draft the published attributes are shown read-only. Leaving the tab or the page
 *   with unsaved text asks through `confirm()`.
 * - Versions: every version with its status, local publish time, publisher and summary; choosing
 *   one previews its attributes.
 *
 * Controls render only with `item_type.edit` (drafts, definition) or `item_type.publish`
 * (Publish); the server checks every call.
 */
import type { AttributeDefinition, ItemTypeOut, ItemTypeVersionListItem, ItemTypeVersionOut } from "@aip/api-client";
import {
  Button,
  confirm,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  ErrorState,
  FormField,
  Input,
  Label,
  LoadingState,
  RecordDetail,
  StatusChip,
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  toast,
  type RecordTab,
  type RequestError,
  type Translate,
} from "@aip/ui";
import { Link, useBlocker } from "@tanstack/react-router";
import { useEffect, useId, useMemo, useState, type FormEvent } from "react";
import { t } from "../shell/t";
import {
  errorCode,
  requestId,
  useCategories,
  useContentType,
  useCreateDraft,
  useDiscardDraft,
  useItemType,
  usePublishDraft,
  useSaveDraft,
  useUpdateItemType,
  useVersion,
  useVersions,
} from "./api";
import { formatAttributes, parseAttributes, type Attribute } from "./attributes";
import { AttributeJsonEditor, type AttributeIssue } from "./AttributeJsonEditor";
import { CheckField } from "./ContentTypeDialog";
import { FieldPreview } from "./FieldPreview";
import { ATTRIBUTE_FIELD_TYPES } from "./fieldTypes";

export const ITEM_TYPE_TABS = ["details", "schema", "versions"] as const;
export type ItemTypeTab = (typeof ITEM_TYPE_TABS)[number];

export function validateItemTypeSearch(search: Record<string, unknown>): { tab?: ItemTypeTab } {
  const tab = search.tab;
  return typeof tab === "string" && (ITEM_TYPE_TABS as readonly string[]).includes(tab) ? { tab: tab as ItemTypeTab } : {};
}

function confirmLeave(): Promise<boolean> {
  return confirm({
    titleKey: "item_types.editor.leave.title",
    bodyKey: "item_types.editor.leave.body",
    confirmKey: "item_types.editor.leave.submit",
    tone: "danger",
  });
}

function saveError(response: { headers: Headers }): string {
  const id = requestId(response);
  return id ? `${t("item_types.error.save")} ${t("item_types.error.request_id", { id })}` : t("item_types.error.save");
}

// ADR 0025: instants are shown in the viewer's own time zone.
const publishedFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export interface ItemTypeEditorProps {
  contentTypeId: string;
  itemTypeId: string;
  permissions: readonly string[];
  tab: ItemTypeTab | undefined;
  onTabChange: (tab: ItemTypeTab) => void;
}

export function ItemTypeEditor({ contentTypeId, itemTypeId, permissions, tab, onTabChange }: ItemTypeEditorProps) {
  const query = useItemType(itemTypeId);
  const contentType = useContentType(contentTypeId);
  const [dirty, setDirty] = useState(false);

  // Leaving the page asks here; a tab change (same path, new `?tab=`) asks in `changeTab`.
  useBlocker({
    shouldBlockFn: async ({ current, next }) => current.pathname !== next.pathname && !(await confirmLeave()),
    enableBeforeUnload: () => dirty,
    disabled: !dirty,
  });

  const response = query.data;
  if (query.isPending || (query.isError && query.isFetching)) {
    return (
      <main className="item-types-page" aria-busy="true">
        <LoadingState variant="spinner" translate={t} />
      </main>
    );
  }
  // An item type of another content type is treated as missing, like another tenant's.
  const mismatched = response?.status === 200 && response.data.contentTypeId !== contentTypeId;
  if (query.isError || response === undefined || response.status !== 200 || mismatched) {
    const error: RequestError = mismatched ? { status: 404 } : response ? { status: response.status, requestId: requestId(response) } : {};
    return (
      <main className="item-types-page">
        <ErrorState error={error} onRetry={() => void query.refetch()} translate={t} />
      </main>
    );
  }
  const itemType = response.data;
  const canEdit = permissions.includes("item_type.edit");
  const canPublish = permissions.includes("item_type.publish");
  const contentTypeName = contentType.data?.status === 200 ? contentType.data.data.name : "";
  const current: ItemTypeTab = tab ?? "details";

  async function changeTab(next: string) {
    if (next === current) return;
    if (dirty && !(await confirmLeave())) return;
    setDirty(false);
    onTabChange(next as ItemTypeTab);
  }

  const tabs: RecordTab[] = [
    { id: "details", content: <ItemTypeForm key={itemType.syncVersion} itemType={itemType} canEdit={canEdit} onReload={() => void query.refetch()} /> },
    {
      id: "schema",
      labelKey: "item_types.tab.schema",
      content: <SchemaTab itemType={itemType} canEdit={canEdit} canPublish={canPublish} onDirtyChange={setDirty} />,
    },
    { id: "versions", labelKey: "item_types.tab.versions", content: <VersionsTab itemTypeId={itemType.id} /> },
  ];

  const published = itemType.publishedVersion ?? null;
  // RecordDetail translates the status key without parameters; the version number goes in here.
  const translate: Translate = (key, params) =>
    key === "item_types.status.published" ? t(key, { version: published ?? "" }) : t(key, params);

  return (
    <main className="item-types-page">
      <RecordDetail
        id={itemType.key}
        title={itemType.name}
        breadcrumb={
          <nav aria-label={t("item_types.breadcrumb")} className="item-types-breadcrumb">
            <Link to="/admin/content-types">{t("item_types.register.title")}</Link>
            <span aria-hidden="true">{t("item_types.breadcrumb.separator")}</span>
            <Link to="/admin/content-types/$contentTypeId" params={{ contentTypeId }} search={{ tab: "item-types" }}>
              {contentTypeName || t("item_types.content_type.title")}
            </Link>
          </nav>
        }
        status={
          published
            ? { tone: "success", icon: "check", labelKey: "item_types.status.published" }
            : { tone: "neutral", icon: "minus", labelKey: "item_types.status.not_published" }
        }
        tabs={tabs}
        tab={current}
        onTabChange={(next) => void changeTab(next)}
        railKey="item-type"
        translate={translate}
      />
    </main>
  );
}

// ---- Details -------------------------------------------------------------------------------

function ItemTypeForm({ itemType, canEdit, onReload }: { itemType: ItemTypeOut; canEdit: boolean; onReload: () => void }) {
  const update = useUpdateItemType();
  const categories = useCategories(itemType.contentTypeId);
  const [name, setName] = useState(itemType.name);
  const [description, setDescription] = useState(itemType.description ?? "");
  const [isComponent, setIsComponent] = useState(itemType.isComponent);
  const [allowsComponents, setAllowsComponents] = useState(itemType.allowsComponents);
  const [nameError, setNameError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const categoryName =
    (categories.data?.status === 200 ? categories.data.data.items : []).find((c) => c.id === itemType.categoryId)?.name ?? "";

  if (!canEdit) {
    const rows: [string, string, boolean][] = [
      ["item_types.item_type.field.key", itemType.key, true],
      ["item_types.item_type.field.category", categoryName, false],
      ["item_types.item_type.field.name", itemType.name, false],
      ["item_types.item_type.field.description", itemType.description ?? "", false],
      ["item_types.item_type.field.is_component", t(itemType.isComponent ? "item_types.yes" : "item_types.no"), false],
      ["item_types.item_type.field.allows_components", t(itemType.allowsComponents ? "item_types.yes" : "item_types.no"), false],
    ];
    return (
      <section aria-labelledby="item-type-facts">
        <h2 id="item-type-facts">{t("item_types.item_type.details")}</h2>
        <dl className="item-types-facts">
          {rows.map(([key, value, mono]) => (
            <div key={key} className="item-types-facts__row">
              <dt>{t(key)}</dt>
              <dd className={mono ? "item-types-mono" : undefined}>{value || "—"}</dd>
            </div>
          ))}
        </dl>
      </section>
    );
  }
  if (conflict) return <ErrorState error={{ status: 409 }} onRetry={onReload} translate={t} />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (!name.trim()) {
      setNameError(t("item_types.error.name"));
      return;
    }
    setNameError(null);
    const response = await update.mutateAsync({
      itemTypeId: itemType.id,
      data: { syncVersion: itemType.syncVersion, name: name.trim(), description: description.trim() || null, isComponent, allowsComponents },
    });
    if (response.status === 200) {
      toast.success("item_types.item_type.saved", { name: response.data.name });
      return;
    }
    if (errorCode(response.data) === "VERSION_CONFLICT") {
      setConflict(true);
      return;
    }
    setFormError(saveError(response));
  }

  return (
    <form className="item-types-form" noValidate aria-labelledby="item-type-form-title" onSubmit={(e) => void submit(e)}>
      <h2 id="item-type-form-title">{t("item_types.item_type.details")}</h2>
      <FormField label={t("item_types.item_type.field.key")} hint={t("item_types.field.key_fixed")}>
        {(control) => <Input {...control} className="item-types-mono" value={itemType.key} readOnly />}
      </FormField>
      <FormField label={t("item_types.item_type.field.category")}>
        {(control) => <Input {...control} value={categoryName} readOnly />}
      </FormField>
      <FormField label={t("item_types.item_type.field.name")} {...(nameError ? { error: nameError } : {})}>
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
        <Button type="submit" disabled={update.isPending}>
          {t("item_types.action.save")}
        </Button>
      </div>
    </form>
  );
}

// ---- Schema --------------------------------------------------------------------------------

/** Turn a 422 body into editor issues: the domain `issues`, or Pydantic's `detail` locations. */
function issuesFrom(data: unknown): AttributeIssue[] | null {
  if (typeof data !== "object" || data === null) return null;
  const body = data as { code?: unknown; issues?: unknown; detail?: unknown };
  if (body.code === "ATTRIBUTES_INVALID" && Array.isArray(body.issues)) {
    return (body.issues as { path?: unknown; code?: unknown }[])
      .filter((i) => typeof i.path === "string" && typeof i.code === "string")
      .map((i) => ({ path: i.path as string, code: i.code as string }));
  }
  if (Array.isArray(body.detail)) {
    const issues: AttributeIssue[] = [];
    for (const item of body.detail as { loc?: unknown }[]) {
      const loc = Array.isArray(item.loc) ? (item.loc as unknown[]) : [];
      if (loc[0] !== "body" || loc[1] !== "attributes") continue;
      const path = loc
        .slice(1)
        .reduce<string>((acc, part) => (typeof part === "number" ? `${acc}[${part}]` : acc ? `${acc}.${String(part)}` : String(part)), "");
      issues.push({ path, code: "ATTRIBUTE_SHAPE_INVALID" });
    }
    return issues.length > 0 ? issues : null;
  }
  return null;
}

interface SchemaTabProps {
  itemType: ItemTypeOut;
  canEdit: boolean;
  canPublish: boolean;
  onDirtyChange: (dirty: boolean) => void;
}

function SchemaTab({ itemType, canEdit, canPublish, onDirtyChange }: SchemaTabProps) {
  const draftQuery = useVersion(itemType.id, itemType.draftVersionId);
  const publishedQuery = useVersion(itemType.id, itemType.publishedVersionId);
  const draft = itemType.draftVersionId && draftQuery.data?.status === 200 ? draftQuery.data.data : undefined;
  const published = itemType.publishedVersionId && publishedQuery.data?.status === 200 ? publishedQuery.data.data : undefined;
  const source: ItemTypeVersionOut | undefined = draft ?? published;
  const sourceKey = source ? `${source.id}:${source.syncVersion}` : "none";
  const sourceText = useMemo(() => formatAttributes(source?.attributes ?? []), [source]);

  // The user's text belongs to the version it was typed against: a save (new syncVersion) or a
  // discard drops it and the editor shows the server's copy again.
  const [edited, setEdited] = useState<{ key: string; text: string } | null>(null);
  const text = edited && edited.key === sourceKey ? edited.text : sourceText;
  const dirty = draft !== undefined && text !== sourceText;
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

  const parsed = useMemo(() => parseAttributes(text), [text]);
  const [lastValid, setLastValid] = useState<{ text: string; attributes: Attribute[] }>({ text: "", attributes: [] });
  if (parsed.ok && lastValid.text !== text) setLastValid({ text, attributes: parsed.attributes });
  const previewAttributes = parsed.ok ? parsed.attributes : lastValid.attributes;

  const [issues, setIssues] = useState<AttributeIssue[]>([]);
  const [conflict, setConflict] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const createDraft = useCreateDraft();
  const save = useSaveDraft();
  const discard = useDiscardDraft();
  const busy = createDraft.isPending || save.isPending || discard.isPending;
  const previewTitle = useId();

  const loading =
    (Boolean(itemType.draftVersionId) && draftQuery.isPending) ||
    (!itemType.draftVersionId && Boolean(itemType.publishedVersionId) && publishedQuery.isPending);
  if (loading) return <LoadingState variant="skeleton" translate={t} />;
  if (conflict) {
    return (
      <ErrorState
        error={{ status: 409 }}
        onRetry={() => {
          setConflict(false);
          setEdited(null);
          void draftQuery.refetch();
        }}
        translate={t}
      />
    );
  }

  async function onCreateDraft() {
    const response = await createDraft.mutateAsync({ itemTypeId: itemType.id });
    if (response.status === 201) {
      setIssues([]);
      toast.success("item_types.editor.draft_created");
    } else if (errorCode(response.data) === "DRAFT_EXISTS") toast.info("item_types.editor.draft_exists");
    else toast.error("item_types.error.save");
  }

  async function onSave() {
    if (!draft) return;
    if (!parsed.ok || parsed.hints.some((h) => h.key === "item_types.hint.not_an_array")) {
      toast.error("item_types.editor.fix_json");
      return;
    }
    // The raw array, so the server's paths match the text even if an item is not an object.
    const attributes = JSON.parse(text) as AttributeDefinition[];
    const response = await save.mutateAsync({
      itemTypeId: itemType.id,
      versionId: draft.id,
      data: { syncVersion: draft.syncVersion, attributes },
    });
    if (response.status === 200) {
      setIssues([]);
      setEdited(null);
      toast.success("item_types.editor.saved");
      return;
    }
    if (errorCode(response.data) === "VERSION_CONFLICT") {
      setConflict(true);
      return;
    }
    const found = issuesFrom(response.data);
    if (found) setIssues(found);
    else toast.error("item_types.error.save");
  }

  async function onDiscard() {
    if (!draft) return;
    const ok = await confirm({
      titleKey: "item_types.editor.discard.title",
      bodyKey: "item_types.editor.discard.body",
      confirmKey: "item_types.editor.discard.submit",
      tone: "danger",
    });
    if (!ok) return;
    const response = await discard.mutateAsync({ itemTypeId: itemType.id, versionId: draft.id });
    if (response.status === 204) {
      setIssues([]);
      setEdited(null);
      toast.success("item_types.editor.discarded");
    } else toast.error("item_types.error.save");
  }

  const actions =
    canEdit || canPublish ? (
      <>
        {canEdit && !draft ? (
          <Button disabled={busy} onClick={() => void onCreateDraft()}>
            {t("item_types.editor.create_draft")}
          </Button>
        ) : null}
        {canEdit && draft ? (
          <>
            <Button variant="secondary" disabled={!parsed.ok} onClick={() => parsed.ok && setEdited({ key: sourceKey, text: formatAttributes(JSON.parse(text) as unknown[]) })}>
              {t("item_types.editor.format")}
            </Button>
            <Button disabled={busy} onClick={() => void onSave()}>
              {t("item_types.editor.save_draft")}
            </Button>
            <Button variant="danger" disabled={busy} onClick={() => void onDiscard()}>
              {t("item_types.editor.discard_draft")}
            </Button>
          </>
        ) : null}
        {canPublish && draft ? (
          <Button variant="secondary" disabled={busy || dirty} onClick={() => setPublishing(true)}>
            {t("item_types.editor.publish")}
          </Button>
        ) : null}
      </>
    ) : undefined;

  const note = draft
    ? dirty && canPublish
      ? t("item_types.editor.save_before_publish")
      : undefined
    : published
      ? t("item_types.editor.published_read_only", { version: published.version })
      : t("item_types.editor.no_draft");

  return (
    <div className="item-types-schema">
      <div className="item-types-schema__editor">
        <AttributeJsonEditor
          value={text}
          onChange={(value) => setEdited({ key: sourceKey, text: value })}
          readOnly={!draft || !canEdit}
          parseError={parsed.ok ? null : parsed.error}
          hints={parsed.hints}
          issues={issues}
          actions={actions}
          {...(note ? { note } : {})}
        />
        <p className="item-types-json__note">
          {t("item_types.editor.field_types", { list: ATTRIBUTE_FIELD_TYPES.map((f) => f.key).join(", ") })}
        </p>
      </div>
      <section className="item-types-schema__preview" aria-labelledby={previewTitle}>
        <h3 id={previewTitle}>{t("item_types.preview.title")}</h3>
        {parsed.ok ? null : (
          <p role="alert" className="aip-form-field__error">
            {t("item_types.editor.parse_error", { line: parsed.error.line, column: parsed.error.column })}
          </p>
        )}
        <FieldPreview attributes={previewAttributes} labelledBy={previewTitle} />
      </section>
      {publishing && draft ? (
        <PublishDialog
          itemTypeId={itemType.id}
          draft={draft}
          onClose={() => setPublishing(false)}
          onIssues={(found) => {
            setIssues(found);
            setPublishing(false);
          }}
          onConflict={() => {
            setPublishing(false);
            setConflict(true);
          }}
        />
      ) : null}
    </div>
  );
}

interface PublishDialogProps {
  itemTypeId: string;
  draft: ItemTypeVersionOut;
  onClose: () => void;
  onIssues: (issues: AttributeIssue[]) => void;
  onConflict: () => void;
}

function PublishDialog({ itemTypeId, draft, onClose, onIssues, onConflict }: PublishDialogProps) {
  const publish = usePublishDraft();
  const [summary, setSummary] = useState(draft.changeSummary ?? "");
  const [formError, setFormError] = useState<string | null>(null);
  const summaryId = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const response = await publish.mutateAsync({
      itemTypeId,
      versionId: draft.id,
      data: { syncVersion: draft.syncVersion, changeSummary: summary.trim() || null },
    });
    if (response.status === 200) {
      toast.success("item_types.editor.published", { version: response.data.version });
      onClose();
      return;
    }
    if (errorCode(response.data) === "VERSION_CONFLICT") {
      onConflict();
      return;
    }
    const found = issuesFrom(response.data);
    if (found) onIssues(found);
    else setFormError(saveError(response));
  }

  return (
    <Dialog open onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent closeLabel={t("ui.close")}>
        <DialogTitle>{t("item_types.editor.publish.title", { version: draft.version })}</DialogTitle>
        <DialogDescription>{t("item_types.editor.publish.body")}</DialogDescription>
        <form className="item-types-form" noValidate onSubmit={(e) => void submit(e)}>
          <Label htmlFor={summaryId}>{t("item_types.editor.publish.summary")}</Label>
          <textarea id={summaryId} className="item-types-summary" rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
          {formError ? (
            <p role="alert" className="aip-form-field__error">
              {formError}
            </p>
          ) : null}
          <div className="item-types-form__actions">
            <Button type="submit" disabled={publish.isPending}>
              {t("item_types.editor.publish.submit")}
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

// ---- Versions ------------------------------------------------------------------------------

function VersionsTab({ itemTypeId }: { itemTypeId: string }) {
  const versions = useVersions(itemTypeId);
  const [selected, setSelected] = useState<string | null>(null);
  const previewTitle = useId();
  if (versions.isPending) return <LoadingState variant="skeleton" translate={t} />;
  if (versions.data?.status !== 200) {
    return <ErrorState error={versions.data ? { status: versions.data.status } : {}} onRetry={() => void versions.refetch()} translate={t} />;
  }
  const items: readonly ItemTypeVersionListItem[] = versions.data.data.items;
  const chosen = items.find((v) => v.id === selected);
  if (items.length === 0) return <p>{t("item_types.empty.versions")}</p>;

  return (
    <section className="item-types-tab" aria-labelledby={`${previewTitle}-list`}>
      <h2 id={`${previewTitle}-list`}>{t("item_types.tab.versions")}</h2>
      <div className="item-types-table">
        <Table>
          <TableCaption>{t("item_types.version.caption")}</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>{t("item_types.version.field.version")}</TableHead>
              <TableHead>{t("item_types.version.field.status")}</TableHead>
              <TableHead>{t("item_types.version.field.published_at")}</TableHead>
              <TableHead>{t("item_types.version.field.published_by")}</TableHead>
              <TableHead>{t("item_types.version.field.summary")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((v) => (
              <TableRow key={v.id}>
                <TableCell>
                  <Button variant="ghost" aria-pressed={v.id === selected} onClick={() => setSelected(v.id === selected ? null : v.id)}>
                    {t("item_types.version.label", { version: v.version })}
                  </Button>
                </TableCell>
                <TableCell>
                  <StatusChip
                    tone={v.status === "published" ? "success" : "neutral"}
                    icon={v.status === "published" ? "check" : "minus"}
                    label={t(`item_types.version.status.${v.status}`)}
                  />
                </TableCell>
                <TableCell>
                  {v.publishedAt ? <time dateTime={v.publishedAt}>{publishedFormat.format(new Date(v.publishedAt))}</time> : "—"}
                </TableCell>
                <TableCell className="item-types-mono">{v.publishedBy ?? "—"}</TableCell>
                <TableCell>{v.changeSummary ?? ""}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {chosen ? (
        <section aria-labelledby={previewTitle} className="item-types-version-preview">
          <h3 id={previewTitle}>{t("item_types.version.preview", { version: chosen.version })}</h3>
          <FieldPreview attributes={chosen.attributes} labelledBy={previewTitle} />
        </section>
      ) : null}
    </section>
  );
}
