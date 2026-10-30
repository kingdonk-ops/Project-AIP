/**
 * The Revisions tab (FORMS-04): every revision newest first (number, status, change note, published
 * and created in the viewer's local time) and, below, the outline of the one chosen with View
 * (`?rev=n`; by default the open draft, else the current revision).
 */
import { useFormsRevisionsGet, type RevisionSummary } from "@aip/api-client";
import { Button, ErrorState, LoadingState, type RequestError } from "@aip/ui";
import { t } from "../shell/t";
import { LocalTime, RevisionStatusChip, revisionLabel } from "./columns";
import { RevisionOutline } from "./RevisionOutline";

export function newestFirst(revisions: readonly RevisionSummary[]): RevisionSummary[] {
  return [...revisions].sort((a, b) => b.revisionNo - a.revisionNo);
}

/** The revision shown by default: the open draft, else the published one, else the newest. */
export function defaultRevision(revisions: readonly RevisionSummary[]): RevisionSummary | undefined {
  const sorted = newestFirst(revisions);
  return sorted.find((r) => r.status === "draft") ?? sorted.find((r) => r.status === "published") ?? sorted[0];
}

function SelectedRevision({ revisionId }: { revisionId: string }) {
  const query = useFormsRevisionsGet(revisionId, { query: { retry: false } });
  const response = query.data;
  if (query.isPending) return <LoadingState variant="spinner" translate={t} />;
  if (query.isError || response === undefined || response.status !== 200) {
    const error: RequestError = response
      ? { status: response.status, requestId: response.headers.get("x-request-id") }
      : {};
    return <ErrorState error={error} onRetry={() => void query.refetch()} translate={t} />;
  }
  return <RevisionOutline revision={response.data} />;
}

export interface RevisionHistoryProps {
  revisions: readonly RevisionSummary[];
  selectedNo: number | undefined;
  onSelect: (revisionNo: number) => void;
}

export function RevisionHistory({ revisions, selectedNo, onSelect }: RevisionHistoryProps) {
  const sorted = newestFirst(revisions);
  const selected = sorted.find((r) => r.revisionNo === selectedNo) ?? defaultRevision(revisions);
  return (
    <div className="forms-history">
      <div className="aip-table__wrap">
        <table className="aip-table forms-history__table">
          <caption className="aip-table__caption">{t("forms.templates.history.caption")}</caption>
          <thead className="aip-table__header">
            <tr className="aip-table__row">
              <th scope="col" className="aip-table__head">
                {t("forms.templates.history.revision")}
              </th>
              <th scope="col" className="aip-table__head">
                {t("forms.templates.history.status")}
              </th>
              <th scope="col" className="aip-table__head">
                {t("forms.templates.history.change_note")}
              </th>
              <th scope="col" className="aip-table__head">
                {t("forms.templates.history.published_at")}
              </th>
              <th scope="col" className="aip-table__head">
                {t("forms.templates.history.created_at")}
              </th>
              <th scope="col" className="aip-table__head">
                {t("forms.templates.history.actions")}
              </th>
            </tr>
          </thead>
          <tbody className="aip-table__body">
            {sorted.map((revision) => {
              const current = revision.id === selected?.id;
              return (
                <tr
                  key={revision.id}
                  className="aip-table__row"
                  data-revision={revision.revisionNo}
                  {...(current ? { "aria-current": "true" as const } : {})}
                >
                  <th scope="row" className="aip-table__cell forms-mono">
                    {revisionLabel(revision.revisionNo)}
                  </th>
                  <td className="aip-table__cell">
                    <RevisionStatusChip status={revision.status} />
                  </td>
                  <td className="aip-table__cell">{revision.changeNote ?? ""}</td>
                  <td className="aip-table__cell">
                    <LocalTime value={revision.publishedAt} />
                  </td>
                  <td className="aip-table__cell">
                    <LocalTime value={revision.createdAt} />
                  </td>
                  <td className="aip-table__cell">
                    {current ? (
                      <span className="forms-history__viewing">
                        {t("forms.templates.history.viewing", { n: revision.revisionNo })}
                      </span>
                    ) : (
                      <Button variant="ghost" onClick={() => onSelect(revision.revisionNo)}>
                        {t("forms.templates.history.view", { n: revision.revisionNo })}
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {selected ? <SelectedRevision key={selected.id} revisionId={selected.id} /> : null}
    </div>
  );
}
