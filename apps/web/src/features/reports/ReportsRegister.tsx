/**
 * The report register (REPORTS-04) on DESIGN-03's `RegisterTable`: the tenant's rendered reports
 * newest first, Status as a quick filter, search over the record label and template key, cursor
 * paging and a column chooser (Error hidden by default). Filter and search live in the URL (see
 * `search.ts`). A succeeded report downloads through `GET /reports/renders/{id}/file`.
 */
import { useReportsRendersList, type RenderJobView } from "@aip/api-client";
import { RegisterTable, type RegisterFilter, type RegisterQuery, type RegisterQueryResult, type Translate } from "@aip/ui";
import { useMemo } from "react";
import { t } from "../shell/t";
import { reportColumns } from "./columns";
import { REPORT_STATUSES, toListParams } from "./search";

/** The register's generic labels, worded for reports. */
const REPORT_TERMS: Readonly<Record<string, string>> = {
  "register.search": "report.register.search",
  "register.any": "report.register.status_all",
  "register.clearAll": "report.register.clear",
  "register.empty": "report.register.filtered_empty",
  "register.loading": "report.register.loading",
  "register.error": "report.register.error",
  "register.reference": "report.register.request_id",
  "register.retry": "report.register.retry",
  "register.previous": "report.register.previous",
  "register.next": "report.register.next",
  "register.pagination": "report.register.pagination",
};

const translate: Translate = (key, params) => t(REPORT_TERMS[key] ?? key, params);

const filters: readonly RegisterFilter[] = [
  {
    id: "status",
    kind: "select",
    labelKey: "report.register.status",
    quick: true,
    options: REPORT_STATUSES.map((value) => ({ value, labelKey: `report.render.status.${value}` })),
  },
];

function useReportsPage(query: RegisterQuery): RegisterQueryResult<RenderJobView> {
  const list = useReportsRendersList(toListParams(query));
  const response = list.data;
  const failed = response !== undefined && response.status !== 200;
  return {
    data: response?.status === 200 ? response.data : undefined,
    isPending: list.isPending,
    isError: list.isError || failed,
    refetch: () => void list.refetch(),
    requestId: failed ? response.headers.get("x-request-id") : null,
  };
}

export interface ReportsRegisterProps {
  query: RegisterQuery;
  permissions: readonly string[];
  /** Replace the URL search (the route navigates with `replace: true`). */
  onQueryChange: (next: RegisterQuery) => void;
}

export function ReportsRegister({ query, permissions, onQueryChange }: ReportsRegisterProps) {
  const columns = useMemo(() => reportColumns(), []);
  const filtered = Object.keys(query.filters).length > 0 || Boolean(query.q);

  return (
    <section className="reports-register" aria-labelledby="reports-title">
      <h1 id="reports-title">{t("report.register.title")}</h1>
      <RegisterTable<RenderJobView>
        id="reports"
        captionKey="report.register.caption"
        columns={columns}
        filters={filters}
        query={query}
        onQueryChange={onQueryChange}
        useQuery={useReportsPage}
        rowId={(r) => r.id}
        permissions={permissions}
        translate={translate}
        empty={filtered ? undefined : <p>{t("report.register.empty")}</p>}
      />
    </section>
  );
}
