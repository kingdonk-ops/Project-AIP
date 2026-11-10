/**
 * The form designer (FORMS-11) at `/templates/$templateId/revisions/$rev/design`: builds a draft
 * revision's sections and fields without JSON. A toolbar (back, code and name, revision, saved
 * state, Undo, Redo, Design | Preview | JSON, Save draft, Publish), then the palette, the canvas
 * with the lint panel under it, and the properties pane. Under 1024 px the palette and properties
 * open as `Blade`s from the toolbar.
 *
 * It edits the FORMS-01 contract and nothing else: logic it cannot edit yet is kept unchanged.
 * Saving sends `PUT /forms/revisions/{id}` with the template's `syncVersion`, so a second editor
 * gets a conflict instead of overwriting; the server lint (live, and on save and publish) is the
 * check. A published or superseded revision, or a user without `form.manage`, opens read-only.
 */
import {
  formsRevisionsGet,
  getFormsRevisionsGetQueryKey,
  getFormsTemplatesGetQueryKey,
  getFormsTemplatesListQueryKey,
  useFormsRevisionsGet,
  useFormsRevisionsPublish,
  useFormsRevisionsReplace,
  useFormsTemplatesAddRevision,
  useFormsTemplatesGet,
  type RevisionOut,
  type RevisionReplaceSchema,
  type TemplateDetail,
} from "@aip/api-client";
import type { FieldType, FormSchema } from "@aip/form-renderer";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type UniqueIdentifier,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { Blade, Button, confirm, ErrorState, LoadingState, Panel, toast, type RequestError } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useBlocker } from "@tanstack/react-router";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { t } from "../../shell/t";
import { RevisionStatusChip } from "../columns";
import { lintIssues, requestIssues } from "../issues";
import { JsonInput } from "../JsonInput";
import { parseTemplateJson, type JsonError } from "../templateJson";
import { Canvas, type FocusRequest } from "./Canvas";
import { canRedo, canUndo, createHistory, push, redo, undo, type History } from "./history";
import { keyFromLabel } from "./keys";
import { LintPanel } from "./LintPanel";
import {
  addField,
  addSection,
  allKeys,
  findField,
  findSection,
  issueCounts,
  moveField,
  moveSection,
  removeField,
  removeSection,
  renameKey,
  updateField,
  updateSection,
  type Selection,
} from "./model";
import { Palette, PALETTE_SECTION } from "./Palette";
import { PreviewPane } from "./PreviewPane";
import { PropertiesPane } from "./PropertiesPane";
import { useLiveLint } from "./useLiveLint";
import "./designer.css";

export type DesignerView = "design" | "preview" | "json";
const VIEWS: readonly DesignerView[] = ["design", "preview", "json"];
const NARROW_QUERY = "(max-width: 1023px)";

function useNarrow(): boolean {
  const supported = typeof window !== "undefined" && typeof window.matchMedia === "function";
  const [narrow, setNarrow] = useState(() => supported && window.matchMedia(NARROW_QUERY).matches);
  useEffect(() => {
    if (!supported) return;
    const media = window.matchMedia(NARROW_QUERY);
    const update = () => setNarrow(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [supported]);
  return narrow;
}

function confirmLeave(): Promise<boolean> {
  return confirm({
    titleKey: "forms.designer.leave.title",
    bodyKey: "forms.designer.leave.body",
    confirmKey: "forms.designer.leave.submit",
    tone: "danger",
  });
}

function sameSchema(a: FormSchema, b: FormSchema): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

export interface DesignerPageProps {
  templateId: string;
  rev: number;
  permissions: readonly string[];
  /** Back to the template page (optionally showing revision `rev`). */
  onBack: (rev?: number) => void;
  /** Open the designer of another revision of this template. */
  onOpenRevision: (rev: number) => void;
}

/** Loads the template and the revision numbered `rev`; anything missing is the not-found state. */
export function DesignerPage({ templateId, rev, permissions, onBack, onOpenRevision }: DesignerPageProps) {
  const templateQuery = useFormsTemplatesGet(templateId, { query: { retry: false } });
  const template = templateQuery.data?.status === 200 ? templateQuery.data.data : undefined;
  const summary = template?.revisions.find((r) => r.revisionNo === rev);
  const revisionQuery = useFormsRevisionsGet(summary?.id ?? "", {
    query: { enabled: summary !== undefined, retry: false, refetchOnWindowFocus: false },
  });
  const revision = revisionQuery.data?.status === 200 ? revisionQuery.data.data : undefined;

  if (templateQuery.isPending || (summary && revisionQuery.isPending)) {
    return (
      <main className="dsg" aria-busy="true">
        <LoadingState variant="spinner" translate={t} />
      </main>
    );
  }
  if (!template || !summary || !revision) {
    const response = template ? revisionQuery.data : templateQuery.data;
    const error: RequestError =
      template && !summary
        ? { status: 404 }
        : response
          ? { status: response.status, requestId: response.headers.get("x-request-id") }
          : {};
    return (
      <main className="dsg">
        <ErrorState
          error={error}
          onRetry={() => void (template ? revisionQuery.refetch() : templateQuery.refetch())}
          translate={t}
        />
      </main>
    );
  }
  return (
    <Designer
      key={revision.id}
      template={template}
      revision={revision}
      permissions={permissions}
      onBack={onBack}
      onOpenRevision={onOpenRevision}
    />
  );
}

export interface DesignerProps {
  template: TemplateDetail;
  revision: RevisionOut;
  permissions: readonly string[];
  onBack: (rev?: number) => void;
  onOpenRevision: (rev: number) => void;
}

export function Designer({ template, revision, permissions, onBack, onOpenRevision }: DesignerProps) {
  const queryClient = useQueryClient();
  const replace = useFormsRevisionsReplace();
  const publish = useFormsRevisionsPublish();
  const addRevision = useFormsTemplatesAddRevision();
  const titleId = useId();
  const narrow = useNarrow();

  const canManage = permissions.includes("form.manage");
  const canPublish = permissions.includes("form.publish");
  const isDraft = revision.status === "draft";
  const readOnly = !isDraft || !canManage;

  const [history, setHistory] = useState<History<FormSchema>>(() => createHistory(revision.schema as unknown as FormSchema));
  const schema = history.present;
  const [saved, setSaved] = useState<FormSchema>(schema);
  const dirty = useMemo(() => !sameSchema(schema, saved), [schema, saved]);
  const [selection, setSelection] = useState<Selection>(null);
  // Bumped on every new selection: edits to one item's inputs group into undo steps by it.
  const [selectSerial, setSelectSerial] = useState(0);
  const [follow, setFollow] = useState<ReadonlySet<string>>(() => new Set());
  const [focus, setFocus] = useState<FocusRequest | null>(null);
  const [view, setView] = useState<DesignerView>("design");
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<JsonError | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [propertiesOpen, setPropertiesOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const lint = useLiveLint(schema, !readOnly);
  const counts = useMemo(() => issueCounts(schema, lint.status === "issues" ? lint.issues.map((i) => i.path) : []), [schema, lint]);

  useBlocker({
    shouldBlockFn: async ({ current, next }) => current.pathname !== next.pathname && !(await confirmLeave()),
    enableBeforeUnload: () => dirty,
    disabled: !dirty,
  });

  // --- editing ---------------------------------------------------------------------------------

  function edit(next: FormSchema, group?: string) {
    if (readOnly) return;
    setHistory((h) => push(h, next, group ? { group } : {}));
  }

  function select(next: NonNullable<Selection>) {
    setSelection(next);
    setSelectSerial((n) => n + 1);
    if (narrow) setPropertiesOpen(true);
  }

  function requestFocus(key: string) {
    setFocus((current) => ({ key, n: (current?.n ?? 0) + 1 }));
  }

  function followed(add: string[], remove: string[] = []) {
    setFollow((current) => {
      const next = new Set(current);
      for (const key of remove) next.delete(key);
      for (const key of add) next.add(key);
      return next;
    });
  }

  function addSectionAt() {
    let at = schema.sections.length;
    if (selection?.kind === "section") at = schema.sections.findIndex((s) => s.key === selection.key) + 1;
    if (selection?.kind === "field") {
      const location = findField(schema, selection.key);
      if (location) at = location.sectionIndex + 1;
    }
    const label = t("forms.designer.new_section", { n: schema.sections.length + 1 });
    const result = addSection(schema, at, label);
    edit(result.schema);
    followed([result.key]);
    select({ kind: "section", key: result.key });
    setPaletteOpen(false);
  }

  function addFieldAt(type: FieldType, target?: { section: string; at: number }) {
    let base = schema;
    let sectionKey: string | undefined = target?.section;
    let at = target?.at ?? Number.MAX_SAFE_INTEGER;
    const added: string[] = [];
    if (!sectionKey) {
      if (selection?.kind === "field") {
        const location = findField(schema, selection.key);
        if (location) {
          sectionKey = location.section.key;
          at = location.fieldIndex + 1;
        }
      } else if (selection?.kind === "section" && findSection(schema, selection.key)) {
        sectionKey = selection.key;
      }
      sectionKey ??= schema.sections[schema.sections.length - 1]?.key;
    }
    if (!sectionKey) {
      const created = addSection(base, 0, t("forms.designer.new_section", { n: 1 }));
      base = created.schema;
      sectionKey = created.key;
      added.push(created.key);
    }
    const result = addField(base, type, sectionKey, at, {
      field: t(`item_types.field_type.${type}`),
      option: t("forms.designer.options.new", { n: 1 }),
    });
    edit(result.schema);
    followed([...added, result.key]);
    select({ kind: "field", key: result.key });
    setPaletteOpen(false);
  }

  function setLabel(item: NonNullable<Selection>, label: string) {
    const group = `label-${selectSerial}`;
    let next =
      item.kind === "section" ? updateSection(schema, item.key, { label }) : updateField(schema, item.key, { label });
    if (follow.has(item.key) && label.trim() !== "") {
      const key = keyFromLabel(
        label,
        allKeys(schema).filter((k) => k !== item.key),
      );
      if (key !== item.key) {
        next = renameKey(next, item.key, key);
        followed([key], [item.key]);
        setSelection({ kind: item.kind, key });
      }
    }
    edit(next, group);
  }

  function rename(from: string, to: string) {
    edit(renameKey(schema, from, to), `key-${selectSerial}`);
    followed([], [from]);
    if (selection?.key === from) setSelection({ ...selection, key: to });
  }

  function move(item: NonNullable<Selection>, delta: -1 | 1) {
    if (item.kind === "section") {
      const index = schema.sections.findIndex((s) => s.key === item.key);
      const to = index + delta;
      if (index < 0 || to < 0 || to >= schema.sections.length) return;
      edit(moveSection(schema, item.key, to));
    } else {
      const location = findField(schema, item.key);
      if (!location) return;
      const to = location.fieldIndex + delta;
      if (to >= 0 && to < location.section.fields.length) {
        edit(moveField(schema, item.key, location.section.key, to));
      } else {
        // Past the end of a section: into the neighbouring one.
        const neighbour = schema.sections[location.sectionIndex + delta];
        if (!neighbour) return;
        edit(moveField(schema, item.key, neighbour.key, delta < 0 ? neighbour.fields.length : 0));
      }
    }
    setSelection(item);
    requestFocus(item.key);
  }

  async function remove(item: NonNullable<Selection>) {
    const label =
      item.kind === "section"
        ? (findSection(schema, item.key)?.label ?? item.key)
        : (findField(schema, item.key)?.field.label ?? item.key);
    const result = item.kind === "section" ? removeSection(schema, item.key) : removeField(schema, item.key);
    if (result.schema === schema) return;
    const fieldCount = item.kind === "section" ? (findSection(schema, item.key)?.fields.length ?? 0) : 0;
    if (result.referencedBy.length > 0 || fieldCount > 0) {
      const refs = result.referencedBy.length
        ? t("forms.designer.delete.refs", { keys: result.referencedBy.join(", ") })
        : "";
      const ok = await confirm({
        titleKey: "forms.designer.delete.title",
        bodyKey: item.kind === "section" ? "forms.designer.delete.section_body" : "forms.designer.delete.field_body",
        confirmKey: "forms.designer.delete.submit",
        params: { label: label || item.key, count: fieldCount, refs },
        tone: "danger",
      });
      if (!ok) return;
    }
    edit(result.schema);
    followed([], [item.key]);
    setSelection(null);
  }

  // --- drag and drop ---------------------------------------------------------------------------

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function describe(id: UniqueIdentifier | undefined): string {
    const [kind, key = ""] = String(id ?? "").split(":");
    if (kind === "palette") {
      return key === PALETTE_SECTION ? t("forms.designer.palette.section") : t(`item_types.field_type.${key}`);
    }
    if (kind === "field") return findField(schema, key)?.field.label || key;
    return findSection(schema, key)?.label || key;
  }

  const announcements: Announcements = {
    onDragStart: ({ active }) => t("forms.designer.dnd.picked", { item: describe(active.id) }),
    onDragOver: ({ active, over }) =>
      over ? t("forms.designer.dnd.over", { item: describe(active.id), target: describe(over.id) }) : undefined,
    onDragEnd: ({ active }) => t("forms.designer.dnd.dropped", { item: describe(active.id) }),
    onDragCancel: ({ active }) => t("forms.designer.dnd.cancelled", { item: describe(active.id) }),
  };

  /** Where a drop on `overId` lands: a section and an index in it (or a section index). */
  function dropTarget(overId: string): { section: string; at: number; sectionIndex: number } | null {
    const [kind, key = ""] = overId.split(":");
    if (kind === "field") {
      const location = findField(schema, key);
      return location ? { section: location.section.key, at: location.fieldIndex, sectionIndex: location.sectionIndex } : null;
    }
    const index = schema.sections.findIndex((s) => s.key === key);
    if (index < 0) return null;
    return { section: key, at: schema.sections[index]!.fields.length, sectionIndex: index };
  }

  function onDragEnd({ active, over }: DragEndEvent) {
    if (!over || readOnly) return;
    const [kind, key = ""] = String(active.id).split(":");
    const target = dropTarget(String(over.id));
    if (!target) return;
    if (kind === "palette") {
      if (key === PALETTE_SECTION) {
        const result = addSection(schema, target.sectionIndex, t("forms.designer.new_section", { n: schema.sections.length + 1 }));
        edit(result.schema);
        followed([result.key]);
        select({ kind: "section", key: result.key });
      } else addFieldAt(key as FieldType, target);
    } else if (kind === "field") {
      edit(moveField(schema, key, target.section, target.at));
    } else if (kind === "section") {
      edit(moveSection(schema, key, target.sectionIndex));
    }
  }

  // --- JSON view -------------------------------------------------------------------------------

  function showJson(text?: string) {
    setJsonText(text ?? JSON.stringify(schema, null, 2));
    setJsonError(null);
    setView("json");
  }

  function applyJson() {
    const parsed = parseTemplateJson(jsonText);
    if (!parsed.ok) {
      setJsonError(parsed.error);
      return;
    }
    setJsonError(null);
    edit(parsed.schema as unknown as FormSchema);
    toast.success("forms.designer.json.applied");
  }

  // --- save, reload and publish ----------------------------------------------------------------

  async function refreshTemplate() {
    await queryClient.invalidateQueries({ queryKey: getFormsTemplatesGetQueryKey(template.id) });
    await queryClient.invalidateQueries({ queryKey: getFormsTemplatesListQueryKey().slice(0, 1) });
  }

  async function reload() {
    const response = await formsRevisionsGet(revision.id);
    await refreshTemplate();
    if (response.status !== 200) {
      toast.error("forms.templates.error.action");
      return;
    }
    queryClient.setQueryData(getFormsRevisionsGetQueryKey(revision.id), response);
    const fresh = response.data.schema as unknown as FormSchema;
    setHistory((h) => push(h, fresh));
    setSaved(fresh);
    setView("design");
    toast.info("forms.designer.save.reloaded");
  }

  async function save() {
    if (readOnly || saving) return;
    setSaving(true);
    const sent = schema;
    try {
      const response = await replace.mutateAsync({
        revisionId: revision.id,
        data: { schema: sent as unknown as RevisionReplaceSchema, expectedSyncVersion: template.syncVersion },
      });
      if (response.status === 200) {
        queryClient.setQueryData(getFormsRevisionsGetQueryKey(revision.id), response);
        await refreshTemplate();
        setSaved(sent);
        toast.success("forms.designer.save.done", { n: revision.revisionNo });
        return;
      }
      if ((response.status as number) === 409) {
        toast.error("forms.designer.save.conflict", undefined, {
          action: { labelKey: "forms.designer.save.reload", onSelect: () => void reload() },
        });
        showJson(JSON.stringify(sent, null, 2));
        return;
      }
      const issues = lintIssues(response.data);
      const request = issues.length ? issues : requestIssues(response.data);
      if (request.length) {
        lint.report(request, sent);
        toast.error("forms.designer.save.invalid");
        return;
      }
      toast.error((response.status as number) === 403 ? "forms.templates.error.forbidden" : "forms.templates.error.save");
    } finally {
      setSaving(false);
    }
  }

  let publishBlocked: string | null = null;
  if (dirty) publishBlocked = "forms.designer.publish.blocked.unsaved";
  else if (lint.status === "checking" || lint.status === "idle") publishBlocked = "forms.designer.publish.blocked.checking";
  else if (lint.status !== "clean") publishBlocked = "forms.designer.publish.blocked.issues";

  async function runPublish() {
    if (publishBlocked || saving) return;
    const ok = await confirm({
      titleKey: "forms.templates.publish.confirm.title",
      bodyKey: "forms.templates.publish.confirm.body",
      confirmKey: "forms.templates.publish.confirm.submit",
      params: { n: revision.revisionNo, code: template.code },
    });
    if (!ok) return;
    const response = await publish.mutateAsync({
      revisionId: revision.id,
      data: { expectedSyncVersion: template.syncVersion },
    });
    if (response.status === 200) {
      await queryClient.invalidateQueries({ queryKey: getFormsRevisionsGetQueryKey(revision.id) });
      await refreshTemplate();
      toast.success("forms.templates.publish.done", { n: revision.revisionNo, code: template.code });
      onBack(revision.revisionNo);
      return;
    }
    const issues = lintIssues(response.data);
    if (issues.length) {
      lint.report(issues, schema);
      return;
    }
    if ((response.status as number) === 409) {
      await refreshTemplate();
      toast.error("forms.templates.error.conflict");
      return;
    }
    toast.error((response.status as number) === 403 ? "forms.templates.error.forbidden" : "forms.templates.error.action");
  }

  const openDraft = template.revisions.find((r) => r.status === "draft");

  async function editAsDraft() {
    const response = await addRevision.mutateAsync({
      templateId: template.id,
      data: { schema: schema as unknown as RevisionReplaceSchema },
    });
    if (response.status === 201) {
      await refreshTemplate();
      toast.success("forms.designer.readonly.created", { n: response.data.revisionNo });
      onOpenRevision(response.data.revisionNo);
      return;
    }
    if ((response.status as number) === 409) await refreshTemplate();
    toast.error((response.status as number) === 409 ? "forms.templates.error.conflict" : "forms.templates.error.action");
  }

  // --- keyboard shortcuts ----------------------------------------------------------------------

  const shortcuts = useRef<{ save: () => void; undo: () => void; redo: () => void }>({ save: () => {}, undo: () => {}, redo: () => {} });
  useEffect(() => {
    shortcuts.current = {
      save: () => void save(),
      undo: () => setHistory(undo),
      redo: () => setHistory(redo),
    };
  });
  useEffect(() => {
    if (readOnly) return;
    const onKey = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "z") {
        event.preventDefault();
        if (event.shiftKey) shortcuts.current.redo();
        else shortcuts.current.undo();
      } else if (key === "y") {
        event.preventDefault();
        shortcuts.current.redo();
      } else if (key === "s") {
        event.preventDefault();
        shortcuts.current.save();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [readOnly]);

  // --- layout ----------------------------------------------------------------------------------

  let state = t("forms.designer.state.read_only");
  if (!readOnly) {
    state = saving
      ? t("forms.designer.state.saving")
      : dirty
        ? t("forms.designer.state.unsaved")
        : t("forms.designer.state.saved");
  }

  const palette = <Palette onAddSection={addSectionAt} onAddField={(type) => addFieldAt(type)} />;
  const properties = (
    <PropertiesPane
      schema={schema}
      selection={selection}
      readOnly={readOnly}
      edit={edit}
      setLabel={setLabel}
      rename={rename}
      optionLabel={t("forms.designer.options.new", { n: 1 })}
    />
  );
  const lintPanel = readOnly ? null : <LintPanel lint={lint} schema={schema} onSelect={(item) => {
    setView("design");
    select(item);
    requestFocus(item.key);
  }} />;

  return (
    <main className="dsg" aria-labelledby={titleId} data-testid="designer" data-read-only={readOnly || undefined}>
      <Panel className="dsg-toolbar">
        <div className="dsg-toolbar__title">
          <Link to="/templates/$templateId" params={{ templateId: template.id }} search={{ rev: revision.revisionNo }} className="dsg-toolbar__back">
            {t("forms.designer.back", { code: template.code })}
          </Link>
          <h1 id={titleId} className="dsg-toolbar__heading">
            <code className="forms-mono">{template.code}</code> <span>{template.name}</span>
          </h1>
          <span className="forms-mono dsg-toolbar__rev">{t("forms.templates.revision.label", { n: revision.revisionNo })}</span>
          <RevisionStatusChip status={revision.status} />
          <p role="status" className="dsg-toolbar__state" data-dirty={dirty || undefined}>
            {state}
          </p>
        </div>
        <div className="dsg-toolbar__actions" role="toolbar" aria-label={t("forms.designer.toolbar")}>
          {readOnly ? null : (
            <>
              <Button type="button" variant="ghost" disabled={!canUndo(history)} onClick={() => setHistory(undo)}>
                {t("forms.designer.undo")}
              </Button>
              <Button type="button" variant="ghost" disabled={!canRedo(history)} onClick={() => setHistory(redo)}>
                {t("forms.designer.redo")}
              </Button>
            </>
          )}
          <div role="group" aria-label={t("forms.designer.view.label")} className="dsg-switch">
            {VIEWS.map((v) => (
              <Button
                key={v}
                type="button"
                variant={view === v ? "primary" : "secondary"}
                aria-pressed={view === v}
                onClick={() => (v === "json" ? showJson() : setView(v))}
              >
                {t(`forms.designer.view.${v}`)}
              </Button>
            ))}
          </div>
          {narrow && view === "design" ? (
            <>
              {readOnly ? null : (
                <Button type="button" variant="secondary" onClick={() => setPaletteOpen(true)}>
                  {t("forms.designer.palette.open")}
                </Button>
              )}
              <Button type="button" variant="secondary" onClick={() => setPropertiesOpen(true)}>
                {t("forms.designer.properties.open")}
              </Button>
            </>
          ) : null}
          {readOnly ? null : (
            <Button type="button" variant="secondary" disabled={saving} onClick={() => void save()}>
              {t("forms.designer.save")}
            </Button>
          )}
          {canPublish && isDraft ? (
            <Button
              type="button"
              disabled={publishBlocked !== null || saving || publish.isPending}
              aria-describedby={publishBlocked ? `${titleId}-publish` : undefined}
              onClick={() => void runPublish()}
            >
              {t("forms.templates.publish.button", { n: revision.revisionNo })}
            </Button>
          ) : null}
        </div>
        {canPublish && isDraft && publishBlocked ? (
          <p id={`${titleId}-publish`} className="dsg-toolbar__reason">
            {t(publishBlocked)}
          </p>
        ) : null}
      </Panel>

      {readOnly ? (
        <Panel className="dsg-readonly">
          <p>
            {isDraft
              ? t("forms.designer.readonly.permission")
              : t("forms.designer.readonly.frozen", {
                  n: revision.revisionNo,
                  status: t(`forms.revision.status.${revision.status}`),
                })}
          </p>
          {canManage && !isDraft ? (
            openDraft ? (
              <Button type="button" variant="secondary" onClick={() => onOpenRevision(openDraft.revisionNo)}>
                {t("forms.designer.readonly.open_draft", { n: openDraft.revisionNo })}
              </Button>
            ) : (
              <Button type="button" disabled={addRevision.isPending} onClick={() => void editAsDraft()}>
                {t("forms.designer.readonly.edit_as_draft")}
              </Button>
            )
          ) : null}
        </Panel>
      ) : null}

      <DndContext
        sensors={sensors}
        onDragEnd={onDragEnd}
        accessibility={{ announcements, screenReaderInstructions: { draggable: t("forms.designer.dnd.instructions") } }}
      >
        {view === "design" ? (
          <div className={readOnly ? "dsg-panes dsg-panes--read-only" : "dsg-panes"}>
            {!readOnly && !narrow ? (
              <Panel heading={t("forms.designer.palette.title")} className="dsg-pane dsg-pane--palette">
                {palette}
              </Panel>
            ) : null}
            <div className="dsg-main">
              <Panel heading={t("forms.designer.canvas.title")} className="dsg-pane dsg-pane--canvas">
                <Canvas
                  schema={schema}
                  selection={selection}
                  counts={counts}
                  readOnly={readOnly}
                  onSelect={select}
                  onMove={move}
                  onRemove={(item) => void remove(item)}
                  onAddField={(section) => addFieldAt("text", { section, at: 0 })}
                  focus={focus}
                />
              </Panel>
              {lintPanel}
            </div>
            {narrow ? null : (
              <Panel heading={t("forms.designer.properties.title")} className="dsg-pane dsg-pane--properties">
                {properties}
              </Panel>
            )}
          </div>
        ) : null}

        {narrow ? (
          <>
            {readOnly ? null : (
              <Blade open={paletteOpen} onOpenChange={setPaletteOpen} recordId={template.code} title={t("forms.designer.palette.title")} translate={t}>
                {palette}
              </Blade>
            )}
            <Blade
              open={propertiesOpen && view === "design"}
              onOpenChange={setPropertiesOpen}
              recordId={template.code}
              title={t("forms.designer.properties.title")}
              translate={t}
            >
              {properties}
            </Blade>
          </>
        ) : null}
      </DndContext>

      {view === "preview" ? <PreviewPane schema={schema} /> : null}

      {view === "json" ? (
        <>
          <Panel heading={t("forms.designer.json.title")} className="dsg-json">
            {readOnly ? (
              <pre className="forms-mono dsg-json__pre">{JSON.stringify(schema, null, 2)}</pre>
            ) : (
              <>
                <JsonInput value={jsonText} onChange={setJsonText} error={jsonError} />
                <div className="forms-form__actions">
                  <Button type="button" onClick={applyJson}>
                    {t("forms.designer.json.apply")}
                  </Button>
                </div>
              </>
            )}
          </Panel>
          {lintPanel}
        </>
      ) : null}
    </main>
  );
}
