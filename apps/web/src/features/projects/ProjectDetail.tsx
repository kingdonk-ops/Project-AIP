/**
 * Project detail page (PROJECTS-07) on DESIGN-04's `RecordDetail`. It loads the project and the
 * tenant's sites, shows the record header with the project's status, and offers two tabs: Details
 * (the edit form, read-only without `project.update`) and History — a slot AUDIT-04 fills with the
 * activity timeline. The lifecycle Archive action is shown only with `project.archive` and only
 * while the project is not already archived; the server enforces the same permission.
 *
 * A missing id, or another tenant's id, is a 404 from the API (RLS): the page shows the not-found
 * state, which is also the cross-tenant check in the e2e suite.
 */
import {
  getProjectsGetQueryKey,
  getProjectsListQueryKey,
  useProjectsGet,
  useProjectsUpdate,
  useSitesList,
  type ProjectOut,
} from "@aip/api-client";
import {
  Button,
  confirm,
  EmptyState,
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
import { useMemo } from "react";
import { t } from "../shell/t";
import { PROJECT_STATUS_STYLE } from "./columns";
import { ProjectEditForm } from "./ProjectEditForm";

const SITE_LOOKUP_LIMIT = 200;

function recordStatus(project: ProjectOut): RecordStatus {
  const style = PROJECT_STATUS_STYLE[project.status];
  return { tone: style.tone, icon: style.icon, labelKey: `projects.status.${project.status}` };
}

export interface ProjectDetailProps {
  projectId: string;
  permissions: readonly string[];
}

export function ProjectDetail({ projectId, permissions }: ProjectDetailProps) {
  const query = useProjectsGet(projectId, { query: { retry: false } });
  const sitesList = useSitesList({ limit: SITE_LOOKUP_LIMIT });
  const sites = useMemo(() => (sitesList.data?.status === 200 ? sitesList.data.data.items : []), [sitesList.data]);

  const queryClient = useQueryClient();
  const update = useProjectsUpdate();

  const response = query.data;
  // apiFetch resolves 4xx/5xx as data (with a status), so the query is "pending" only before the
  // first response, and "error" only on a thrown network failure.
  if (query.isPending || (query.isError && query.isFetching)) {
    return (
      <main className="projects-detail" aria-busy="true">
        <LoadingState variant="spinner" translate={t} />
      </main>
    );
  }
  if (query.isError || response === undefined || response.status !== 200) {
    const error: RequestError = response
      ? { status: response.status, requestId: response.headers.get("x-request-id") }
      : {};
    return (
      <main className="projects-detail">
        <ErrorState error={error} onRetry={() => void query.refetch()} translate={t} />
      </main>
    );
  }

  const project = response.data;
  const canArchive = permissions.includes("project.archive");

  async function archive() {
    const ok = await confirm({
      titleKey: "projects.detail.archive.confirm.title",
      bodyKey: "projects.detail.archive.confirm.body",
      confirmKey: "projects.detail.archive.confirm.submit",
      params: { code: project.code },
      tone: "danger",
    });
    if (!ok) return;
    const result = await update.mutateAsync({
      projectId: project.id,
      data: { syncVersion: project.syncVersion, status: "archived" },
    });
    if (result.status === 200) {
      await queryClient.invalidateQueries({ queryKey: getProjectsGetQueryKey(project.id) });
      await queryClient.invalidateQueries({ queryKey: getProjectsListQueryKey().slice(0, 1) });
      toast.success("projects.detail.archived", { code: result.data.code });
      return;
    }
    if ((result.status as number) === 403) {
      toast.error("projects.error.forbidden");
      return;
    }
    if ((result.status as number) === 409) {
      await query.refetch();
      toast.error("projects.error.conflict");
      return;
    }
    toast.error("projects.error.save");
  }

  const tabs: RecordTab[] = [
    { id: "details", content: <ProjectEditForm project={project} sites={sites} permissions={permissions} /> },
    {
      // Slot for AUDIT-04's activity timeline; until then an empty state names what will appear.
      id: "history",
      content: (
        <EmptyState
          icon="clock"
          titleKey="projects.detail.history.empty.title"
          bodyKey="projects.detail.history.empty.body"
          translate={t}
        />
      ),
    },
  ];

  const showArchive = canArchive && project.status !== "archived";

  return (
    <main className="projects-detail">
      <RecordDetail
        id={project.code}
        title={project.name}
        breadcrumb={<Link to="/projects">{t("projects.detail.breadcrumb")}</Link>}
        status={recordStatus(project)}
        tabs={tabs}
        railKey="project"
        actions={
          showArchive ? (
            <Button variant="danger" disabled={update.isPending} onClick={() => void archive()}>
              {t("projects.detail.archive")}
            </Button>
          ) : undefined
        }
        translate={t}
      />
    </main>
  );
}
