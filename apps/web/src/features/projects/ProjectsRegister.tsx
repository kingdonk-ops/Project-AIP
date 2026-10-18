/**
 * The projects register (PROJECTS-02) on DESIGN-03's `RegisterTable` (PROJECTS-06): Status as a
 * quick filter, search, server-side sort both ways on Code, Name and Updated, cursor paging, a
 * column chooser (Region hidden by default) and CSV export through `GET /projects/export.csv`
 * with the same filters and sort. All of it lives in the URL (see `search.ts`); Enter on a row opens
 * the project.
 */
import { getProjectsExportUrl, useProjectsList, useSitesList, type ProjectOut } from "@aip/api-client";
import {
  Button,
  RegisterTable,
  type RegisterFilter,
  type RegisterQuery,
  type RegisterQueryResult,
  type Translate,
} from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { t } from "../shell/t";
import { projectColumns } from "./columns";
import { PROJECT_STATUSES, toExportParams, toListParams } from "./search";

const SITE_LOOKUP_LIMIT = 200;

/** The register's generic labels, worded for projects (the walking skeleton finds them by name). */
const PROJECT_TERMS: Readonly<Record<string, string>> = {
  "register.search": "projects.filter.search",
  "register.any": "projects.filter.status_all",
  "register.clearAll": "projects.filter.clear",
  "register.empty": "projects.empty.filtered",
  "register.loading": "projects.loading",
  "register.error": "projects.error.title",
  "register.reference": "projects.error.request_id",
  "register.retry": "projects.error.retry",
  "register.previous": "projects.page.previous",
  "register.next": "projects.page.next",
  "register.pagination": "projects.page.label",
};

const translate: Translate = (key, params) => t(PROJECT_TERMS[key] ?? key, params);

const filters: readonly RegisterFilter[] = [
  {
    id: "status",
    kind: "select",
    labelKey: "projects.filter.status",
    quick: true,
    options: PROJECT_STATUSES.map((value) => ({ value, labelKey: `projects.status.${value}` })),
  },
];

function useProjectsPage(query: RegisterQuery): RegisterQueryResult<ProjectOut> {
  const list = useProjectsList(toListParams(query));
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

export interface ProjectsRegisterProps {
  query: RegisterQuery;
  /** The code of the project just created, for the confirmation message. */
  created?: string | undefined;
  permissions: readonly string[];
  /** Replace the URL search (the route navigates with `replace: true`). */
  onQueryChange: (next: RegisterQuery) => void;
  /** Enter on a row. */
  onOpenProject: (project: ProjectOut) => void;
}

export function ProjectsRegister({ query, created, permissions, onQueryChange, onOpenProject }: ProjectsRegisterProps) {
  const canCreate = permissions.includes("project.create");
  const sites = useSitesList({ limit: SITE_LOOKUP_LIMIT });
  const siteNames = useMemo(() => {
    const items = sites.data?.status === 200 ? sites.data.data.items : [];
    return new Map(items.map((s) => [s.id, s.name]));
  }, [sites.data]);
  const columns = useMemo(() => projectColumns({ siteNames }), [siteNames]);
  const filtered = Object.keys(query.filters).length > 0 || Boolean(query.q);

  return (
    <section className="projects-register" aria-labelledby="projects-title">
      <div className="projects-register__header">
        <h1 id="projects-title">{t("projects.register.title")}</h1>
        {canCreate ? (
          <Button asChild>
            <Link to="/projects/new">{t("projects.register.create")}</Link>
          </Button>
        ) : null}
      </div>

      {created ? (
        <p role="status" className="projects-register__notice">
          {t("projects.register.created", { code: created })}
        </p>
      ) : null}

      <RegisterTable<ProjectOut>
        id="projects"
        captionKey="projects.register.caption"
        columns={columns}
        filters={filters}
        query={query}
        onQueryChange={onQueryChange}
        useQuery={useProjectsPage}
        rowId={(p) => p.id}
        onOpenRow={onOpenProject}
        permissions={permissions}
        exportHref={(q) => getProjectsExportUrl(toExportParams(q))}
        translate={translate}
        empty={
          filtered ? undefined : (
            <div className="projects-register__empty">
              <p>{t("projects.empty.title")}</p>
              {canCreate ? (
                <Button asChild>
                  <Link to="/projects/new">{t("projects.register.create")}</Link>
                </Button>
              ) : null}
            </div>
          )
        }
      />
    </section>
  );
}
