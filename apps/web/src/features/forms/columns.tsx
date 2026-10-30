/**
 * Shared presentation of form templates and revisions (FORMS-04): status chips, revision labels,
 * local-time formatting and the register's columns.
 */
import type { TemplateListItem } from "@aip/api-client";
import { StatusChip, type IconName, type RegisterColumn, type StatusTone } from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { t } from "../shell/t";

type Style = { tone: StatusTone; icon: IconName };

export const TEMPLATE_STATUS_STYLE: Record<string, Style> = {
  draft: { tone: "neutral", icon: "minus" },
  active: { tone: "success", icon: "check" },
  retired: { tone: "info", icon: "folder" },
};

export const REVISION_STATUS_STYLE: Record<string, Style> = {
  draft: { tone: "warning", icon: "clock" },
  published: { tone: "success", icon: "check" },
  superseded: { tone: "neutral", icon: "minus" },
};

const FALLBACK: Style = { tone: "neutral", icon: "minus" };

export function TemplateStatusChip({ status }: { status: string }) {
  const style = TEMPLATE_STATUS_STYLE[status] ?? FALLBACK;
  return <StatusChip tone={style.tone} icon={style.icon} label={t(`forms.template.status.${status}`)} />;
}

export function RevisionStatusChip({ status }: { status: string }) {
  const style = REVISION_STATUS_STYLE[status] ?? FALLBACK;
  return <StatusChip tone={style.tone} icon={style.icon} label={t(`forms.revision.status.${status}`)} />;
}

export function revisionLabel(n: number | null | undefined): string {
  return n == null ? t("forms.templates.revision.none") : t("forms.templates.revision.label", { n });
}

// ADR 0025: instants are shown in the viewer's own time zone.
const timeFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function LocalTime({ value }: { value: string | null | undefined }) {
  if (!value) return <>{t("forms.templates.history.none")}</>;
  return <time dateTime={value}>{timeFormat.format(new Date(value))}</time>;
}

export function templateColumns(): RegisterColumn<TemplateListItem>[] {
  return [
    {
      id: "code",
      headerKey: "forms.templates.field.code",
      mono: true,
      cell: (row) => (
        <Link to="/templates/$templateId" params={{ templateId: row.id }}>
          {row.code}
        </Link>
      ),
      csv: (row) => row.code,
    },
    { id: "name", headerKey: "forms.templates.field.name", cell: (row) => row.name },
    { id: "kind", headerKey: "forms.templates.field.kind", cell: (row) => t(`forms.kind.${row.kind}`) },
    { id: "status", headerKey: "forms.templates.field.status", cell: (row) => <TemplateStatusChip status={row.status} /> },
    {
      id: "revision",
      headerKey: "forms.templates.field.current_revision",
      cell: (row) => revisionLabel(row.currentRevisionNo),
    },
    { id: "updated", headerKey: "forms.templates.field.updated", cell: (row) => <LocalTime value={row.updatedAt} /> },
  ];
}
