/**
 * Column definitions of the projects register (PROJECTS-02, on `RegisterTable` since PROJECTS-06).
 * Code, Name and Updated sort both ways on the server; Region is hidden until the user shows it.
 */
import type { ProjectOut } from "@aip/api-client";
import { StatusChip, type IconName, type RegisterColumn, type StatusTone } from "@aip/ui";
import { t } from "../shell/t";
import type { ProjectStatus } from "./search";

export interface ProjectRowContext {
  /** Site names by id, for the Site column. */
  siteNames: ReadonlyMap<string, string>;
}

const STATUS_STYLE: Record<ProjectStatus, { tone: StatusTone; icon: IconName }> = {
  draft: { tone: "neutral", icon: "minus" },
  active: { tone: "success", icon: "check" },
  closing: { tone: "warning", icon: "clock" },
  archived: { tone: "info", icon: "folder" },
};

export function ProjectStatusChip({ status }: { status: ProjectStatus }) {
  const style = STATUS_STYLE[status];
  return <StatusChip tone={style.tone} icon={style.icon} label={t(`projects.status.${status}`)} />;
}

// ADR 0025: instants are shown in the viewer's own time zone.
const updatedFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function projectColumns(context: ProjectRowContext): RegisterColumn<ProjectOut>[] {
  return [
    { id: "code", headerKey: "projects.field.code", cell: (p) => p.code, mono: true, sortable: true },
    { id: "name", headerKey: "projects.field.name", cell: (p) => p.name, sortable: true },
    {
      id: "site",
      headerKey: "projects.field.site",
      cell: (p) => (p.siteId ? (context.siteNames.get(p.siteId) ?? "") : ""),
    },
    { id: "region", headerKey: "projects.field.region", cell: (p) => p.region ?? "", defaultVisible: false },
    { id: "status", headerKey: "projects.field.status", cell: (p) => <ProjectStatusChip status={p.status} /> },
    {
      id: "updated",
      headerKey: "projects.field.updated",
      cell: (p) => <time dateTime={p.updatedAt}>{updatedFormat.format(new Date(p.updatedAt))}</time>,
      sortable: true,
    },
  ];
}
