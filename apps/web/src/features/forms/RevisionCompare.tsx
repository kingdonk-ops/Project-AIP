/**
 * The Compare tab (FORMS-04): pick two revisions (From and To, in `?from=&to=`; by default the two
 * newest) and see the structural diff of their sections and fields from `diffSchemas`.
 */
import { useFormsRevisionsGet, type RevisionSummary } from "@aip/api-client";
import { EmptyState, ErrorState, LoadingState, StatusChip, type IconName, type RequestError, type StatusTone } from "@aip/ui";
import { useId } from "react";
import { t } from "../shell/t";
import { canonical, diffSchemas, type ChangeKind, type PropertyChange, type SchemaChange } from "./diff";
import { revisionLabel } from "./columns";
import { newestFirst } from "./RevisionHistory";

const CHANGE_STYLE: Record<ChangeKind, { tone: StatusTone; icon: IconName }> = {
  added: { tone: "success", icon: "check" },
  removed: { tone: "danger", icon: "close" },
  changed: { tone: "warning", icon: "info" },
  moved: { tone: "info", icon: "chevron-down" },
};

const MAX_VALUE = 120;

function show(value: unknown): string {
  if (value === undefined) return t("forms.templates.compare.absent");
  const text = typeof value === "string" ? JSON.stringify(value) : canonical(value);
  return text.length > MAX_VALUE ? `${text.slice(0, MAX_VALUE - 1)}…` : text;
}

function propertyText(p: PropertyChange): string {
  return t("forms.templates.compare.property", { name: p.name, before: show(p.before), after: show(p.after) });
}

function details(change: SchemaChange): string[] {
  const lines: string[] = [];
  if (change.fromSection && change.toSection) {
    lines.push(t("forms.templates.compare.moved_detail", { from: change.fromSection, to: change.toSection }));
  }
  if (change.reordered) lines.push(t("forms.templates.compare.reordered"));
  return [...lines, ...change.properties.map(propertyText)];
}

function useRevision(id: string | undefined) {
  return useFormsRevisionsGet(id ?? "", { query: { enabled: id !== undefined, retry: false } });
}

export interface RevisionCompareProps {
  revisions: readonly RevisionSummary[];
  from: number | undefined;
  to: number | undefined;
  onChange: (next: { from: number; to: number }) => void;
}

export function RevisionCompare({ revisions, from, to, onChange }: RevisionCompareProps) {
  const fromId = useId();
  const toId = useId();
  const sorted = newestFirst(revisions);
  const byNo = new Map(sorted.map((r) => [r.revisionNo, r]));
  const target = (to !== undefined ? byNo.get(to) : undefined) ?? sorted[0];
  const source = (from !== undefined ? byNo.get(from) : undefined) ?? sorted.find((r) => r !== target);

  const a = useRevision(source?.id);
  const b = useRevision(target?.id);

  if (sorted.length < 2 || !source || !target) {
    return (
      <EmptyState
        icon="info"
        titleKey="forms.templates.compare.need_two.title"
        bodyKey="forms.templates.compare.need_two.body"
        translate={t}
      />
    );
  }

  const picker = (
    <div className="forms-compare__pickers">
      <label htmlFor={fromId}>
        {t("forms.templates.compare.from")}
        <select
          id={fromId}
          className="aip-input forms-select"
          value={source.revisionNo}
          onChange={(e) => onChange({ from: Number(e.target.value), to: target.revisionNo })}
        >
          {sorted.map((r) => (
            <option key={r.id} value={r.revisionNo}>
              {revisionLabel(r.revisionNo)}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor={toId}>
        {t("forms.templates.compare.to")}
        <select
          id={toId}
          className="aip-input forms-select"
          value={target.revisionNo}
          onChange={(e) => onChange({ from: source.revisionNo, to: Number(e.target.value) })}
        >
          {sorted.map((r) => (
            <option key={r.id} value={r.revisionNo}>
              {revisionLabel(r.revisionNo)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );

  let body;
  if (a.isPending || b.isPending) {
    body = <LoadingState variant="spinner" translate={t} />;
  } else if (a.data?.status !== 200 || b.data?.status !== 200) {
    const failed = a.data?.status !== 200 ? a.data : b.data;
    const error: RequestError = failed ? { status: failed.status, requestId: failed.headers.get("x-request-id") } : {};
    body = (
      <ErrorState
        error={error}
        onRetry={() => {
          void a.refetch();
          void b.refetch();
        }}
        translate={t}
      />
    );
  } else {
    const { changes, counts } = diffSchemas(a.data.data.schema, b.data.data.schema);
    body = (
      <>
        <p className="forms-compare__summary" role="status">
          {changes.length === 0 ? t("forms.templates.compare.same") : t("forms.templates.compare.summary", { ...counts })}
        </p>
        {changes.length > 0 ? (
          <div className="aip-table__wrap">
            <table className="aip-table forms-compare__table">
              <caption className="aip-table__caption">
                {t("forms.templates.compare.caption", { from: source.revisionNo, to: target.revisionNo })}
              </caption>
              <thead className="aip-table__header">
                <tr className="aip-table__row">
                  {(["change", "item", "key", "section", "details"] as const).map((col) => (
                    <th key={col} scope="col" className="aip-table__head">
                      {t(`forms.templates.compare.col.${col}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="aip-table__body">
                {changes.map((change, index) => {
                  const style = CHANGE_STYLE[change.change];
                  return (
                    <tr
                      key={`${index}-${change.item}-${change.key}`}
                      className="aip-table__row"
                      data-change={change.change}
                      data-key={change.key}
                    >
                      <td className="aip-table__cell">
                        <StatusChip
                          tone={style.tone}
                          icon={style.icon}
                          label={t(`forms.templates.compare.change.${change.change}`)}
                        />
                      </td>
                      <td className="aip-table__cell">{t(`forms.templates.compare.item.${change.item}`)}</td>
                      <td className="aip-table__cell forms-mono">{change.key}</td>
                      <td className="aip-table__cell forms-mono">{change.section ?? ""}</td>
                      <td className="aip-table__cell">
                        <ul className="forms-compare__details">
                          {details(change).map((line) => (
                            <li key={line} className="forms-mono">
                              {line}
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <div className="forms-compare">
      {picker}
      {body}
    </div>
  );
}
