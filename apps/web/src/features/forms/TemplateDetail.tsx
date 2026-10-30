/**
 * The form template detail page (FORMS-04) on DESIGN-04's `RecordDetail`: code, name and status in
 * the header, the kind and current revision under it, and two tabs held in the route search:
 * Revisions (history plus an outline of one revision) and Compare (a structural diff of two).
 *
 * Header actions follow the permissions: with `form.manage`, New draft (no open draft) or Replace
 * draft / Discard draft (an open draft); with `form.publish`, Publish the open draft with the
 * template's `syncVersion`. The server checks each call again. A missing id, or another tenant's id,
 * is a 404 from the API (RLS), shown as the not-found state.
 */
import {
  getFormsRevisionsGetQueryKey,
  getFormsTemplatesGetQueryKey,
  getFormsTemplatesListQueryKey,
  useFormsRevisionsDiscard,
  useFormsRevisionsGet,
  useFormsRevisionsPublish,
  useFormsTemplatesGet,
  type RevisionSummary,
  type TemplateDetail as TemplateDetailData,
} from "@aip/api-client";
import {
  Button,
  confirm,
  ErrorState,
  LoadingState,
  RecordDetail,
  toast,
  type RecordStatus,
  type RecordTab,
  type RequestError,
} from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { t } from "../shell/t";
import { revisionLabel, TEMPLATE_STATUS_STYLE } from "./columns";
import { IssueList } from "./IssueList";
import { lintIssues, type Issue } from "./issues";
import { RevisionCompare } from "./RevisionCompare";
import { RevisionDialog, type RevisionDialogMode } from "./RevisionDialog";
import { RevisionHistory } from "./RevisionHistory";
import type { DetailTab, TemplateSearch } from "./search";

function recordStatus(template: TemplateDetailData): RecordStatus {
  const style = TEMPLATE_STATUS_STYLE[template.status] ?? { tone: "neutral", icon: "minus" };
  return { tone: style.tone, icon: style.icon, labelKey: `forms.template.status.${template.status}` };
}

/** The open draft, if any (FORMS-01 allows one per template). */
function openDraft(revisions: readonly RevisionSummary[]): RevisionSummary | undefined {
  return revisions.find((r) => r.status === "draft");
}

export interface TemplateDetailProps {
  templateId: string;
  permissions: readonly string[];
  search: TemplateSearch;
  /** Merge into the route search (the route navigates with `replace: true`). */
  onSearchChange: (next: TemplateSearch) => void;
}

export function TemplateDetail({ templateId, permissions, search, onSearchChange }: TemplateDetailProps) {
  const query = useFormsTemplatesGet(templateId, { query: { retry: false } });
  const queryClient = useQueryClient();
  const publish = useFormsRevisionsPublish();
  const discard = useFormsRevisionsDiscard();
  const [dialog, setDialog] = useState<"new" | "replace" | null>(null);
  const [publishIssues, setPublishIssues] = useState<Issue[]>([]);

  const response = query.data;
  const template = response?.status === 200 ? response.data : undefined;
  const draft = template ? openDraft(template.revisions) : undefined;
  // The draft's JSON, for Replace draft (only fetched for users who can replace it).
  const canManage = permissions.includes("form.manage");
  const canPublish = permissions.includes("form.publish");
  const draftQuery = useFormsRevisionsGet(draft?.id ?? "", {
    query: { enabled: canManage && draft !== undefined, retry: false },
  });

  if (query.isPending || (query.isError && query.isFetching)) {
    return (
      <main className="forms-detail" aria-busy="true">
        <LoadingState variant="spinner" translate={t} />
      </main>
    );
  }
  if (query.isError || response === undefined || !template) {
    const error: RequestError = response
      ? { status: response.status, requestId: response.headers.get("x-request-id") }
      : {};
    return (
      <main className="forms-detail">
        <ErrorState error={error} onRetry={() => void query.refetch()} translate={t} />
      </main>
    );
  }

  const current = template;

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: getFormsTemplatesGetQueryKey(current.id) });
    await queryClient.invalidateQueries({ queryKey: getFormsTemplatesListQueryKey().slice(0, 1) });
  }

  function failed(status: number) {
    if (status === 403) toast.error("forms.templates.error.forbidden");
    else if (status === 409) toast.error("forms.templates.error.conflict");
    else toast.error("forms.templates.error.action");
  }

  async function runPublish(revision: RevisionSummary) {
    setPublishIssues([]);
    const ok = await confirm({
      titleKey: "forms.templates.publish.confirm.title",
      bodyKey: "forms.templates.publish.confirm.body",
      confirmKey: "forms.templates.publish.confirm.submit",
      params: { n: revision.revisionNo, code: current.code },
    });
    if (!ok) return;
    const result = await publish.mutateAsync({
      revisionId: revision.id,
      data: { expectedSyncVersion: current.syncVersion },
    });
    if (result.status === 200) {
      await queryClient.invalidateQueries({ queryKey: getFormsRevisionsGetQueryKey(revision.id) });
      await refresh();
      toast.success("forms.templates.publish.done", { n: revision.revisionNo, code: current.code });
      onSearchChange({ ...search, rev: revision.revisionNo });
      return;
    }
    const issues = lintIssues(result.data);
    if (issues.length) {
      setPublishIssues(issues);
      return;
    }
    if ((result.status as number) === 409) await refresh();
    failed(result.status);
  }

  async function runDiscard(revision: RevisionSummary) {
    const ok = await confirm({
      titleKey: "forms.templates.draft.discard_confirm.title",
      bodyKey: "forms.templates.draft.discard_confirm.body",
      confirmKey: "forms.templates.draft.discard_confirm.submit",
      params: { n: revision.revisionNo },
      tone: "danger",
    });
    if (!ok) return;
    const result = await discard.mutateAsync({ revisionId: revision.id });
    if ((result.status as number) === 204) {
      setPublishIssues([]);
      await refresh();
      toast.success("forms.templates.draft.discarded", { n: revision.revisionNo });
      const rest = { ...search };
      delete rest.rev;
      onSearchChange(rest);
      return;
    }
    if ((result.status as number) === 409) await refresh();
    failed(result.status);
  }

  const busy = publish.isPending || discard.isPending;
  const draftText =
    draftQuery.data?.status === 200 ? JSON.stringify(draftQuery.data.data.schema, null, 2) : undefined;
  const draftNote = draftQuery.data?.status === 200 ? (draftQuery.data.data.changeNote ?? "") : "";

  const actions = (
    <>
      {canManage && !draft ? (
        <Button variant="secondary" onClick={() => setDialog("new")}>
          {t("forms.templates.draft.new")}
        </Button>
      ) : null}
      {canManage && draft ? (
        <>
          <Button variant="secondary" disabled={draftText === undefined} onClick={() => setDialog("replace")}>
            {t("forms.templates.draft.replace")}
          </Button>
          <Button variant="danger" disabled={busy} onClick={() => void runDiscard(draft)}>
            {t("forms.templates.draft.discard")}
          </Button>
        </>
      ) : null}
      {canPublish && draft ? (
        <Button disabled={busy} onClick={() => void runPublish(draft)}>
          {t("forms.templates.publish.button", { n: draft.revisionNo })}
        </Button>
      ) : null}
    </>
  );

  const tabs: RecordTab[] = [
    {
      id: "revisions",
      labelKey: "forms.templates.detail.tab.revisions",
      content: (
        <>
          <dl className="forms-detail__summary">
            <div>
              <dt>{t("forms.templates.field.kind")}</dt>
              <dd>{t(`forms.kind.${template.kind}`)}</dd>
            </div>
            <div>
              <dt>{t("forms.templates.field.current_revision")}</dt>
              <dd>{revisionLabel(template.currentRevisionNo)}</dd>
            </div>
          </dl>
          <RevisionHistory
            revisions={template.revisions}
            selectedNo={search.rev}
            onSelect={(rev) => onSearchChange({ ...search, rev })}
          />
        </>
      ),
    },
    {
      id: "compare",
      labelKey: "forms.templates.detail.tab.compare",
      content: (
        <RevisionCompare
          revisions={template.revisions}
          from={search.from}
          to={search.to}
          onChange={({ from, to }) => onSearchChange({ ...search, from, to })}
        />
      ),
    },
  ];

  let dialogMode: RevisionDialogMode | null = null;
  if (dialog === "new") {
    dialogMode = { kind: "new", templateId: template.id, code: template.code, canCopy: template.currentRevisionId !== null };
  } else if (dialog === "replace" && draft && draftText !== undefined) {
    dialogMode = {
      kind: "replace",
      revisionId: draft.id,
      revisionNo: draft.revisionNo,
      initialText: draftText,
      initialNote: draftNote,
    };
  }

  return (
    <main className="forms-detail">
      <RecordDetail
        id={template.code}
        title={template.name}
        breadcrumb={<Link to="/templates">{t("forms.templates.detail.breadcrumb")}</Link>}
        status={recordStatus(template)}
        tabs={tabs}
        tab={search.tab ?? "revisions"}
        onTabChange={(tab) => onSearchChange({ ...search, tab: tab as DetailTab })}
        railKey="form-template"
        actions={canManage || canPublish ? actions : undefined}
        translate={t}
      />
      <IssueList issues={publishIssues} titleKey="forms.templates.publish.blocked" />
      {dialogMode ? (
        <RevisionDialog
          key={`${dialog}-${draft?.id ?? "none"}`}
          mode={dialogMode}
          open
          onOpenChange={(open) => {
            if (!open) setDialog(null);
          }}
          onSaved={(n) => {
            setPublishIssues([]);
            void refresh();
            if (draft) void queryClient.invalidateQueries({ queryKey: getFormsRevisionsGetQueryKey(draft.id) });
            if (n !== null) onSearchChange({ ...search, tab: "revisions", rev: n });
          }}
        />
      ) : null}
    </main>
  );
}
