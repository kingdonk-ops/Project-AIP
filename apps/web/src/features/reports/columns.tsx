/**
 * Column definitions of the report register (REPORTS-04). Nothing sorts (the API lists newest
 * first); Error is hidden until the user shows it. The download is a plain same-origin link to the
 * API, which streams the stored PDF after checking `report.view`: the browser never sees a storage
 * URL.
 */
import { getReportsRendersFileUrl, type RenderJobView } from "@aip/api-client";
import { StatusChip, type IconName, type RegisterColumn, type StatusTone } from "@aip/ui";
import { t } from "../shell/t";
import type { ReportStatus } from "./search";

export const REPORT_STATUS_STYLE: Record<ReportStatus, { tone: StatusTone; icon: IconName }> = {
  queued: { tone: "neutral", icon: "clock" },
  running: { tone: "info", icon: "loader" },
  succeeded: { tone: "success", icon: "check" },
  failed: { tone: "danger", icon: "alert" },
};

export function ReportStatusChip({ status }: { status: ReportStatus }) {
  const style = REPORT_STATUS_STYLE[status];
  return <StatusChip tone={style.tone} icon={style.icon} label={t(`report.render.status.${status}`)} />;
}

// ADR 0025: instants are shown in the viewer's own time zone.
const generatedFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** The template's name (a terminology key on the pinned version), else its key. */
export function templateName(report: RenderJobView): string {
  return report.templateNameKey ? t(report.templateNameKey) : report.templateKey;
}

/** The record's label at request time, else its id. */
export function recordName(report: RenderJobView): string {
  return report.recordLabel ?? report.recordId;
}

function generatedAt(report: RenderJobView): string {
  return report.renderedAt ?? report.createdAt;
}

export function reportColumns(): RegisterColumn<RenderJobView>[] {
  return [
    {
      id: "status",
      headerKey: "report.register.column.status",
      cell: (r) => <ReportStatusChip status={r.status} />,
      csv: (r) => r.status,
    },
    {
      id: "template",
      headerKey: "report.register.column.template",
      cell: (r) => (
        <span className="reports-register__stack">
          <span>{templateName(r)}</span>
          <span className="reports-register__meta">
            {t("report.register.template_version", {
              version: r.templateVersion,
              variant: t(`report.register.variant.${r.variant}`),
            })}
          </span>
        </span>
      ),
      csv: (r) => `${r.templateKey} v${r.templateVersion} ${r.variant}`,
    },
    {
      id: "record",
      headerKey: "report.register.column.record",
      cell: (r) => (
        <span className="reports-register__stack">
          <span className={r.recordLabel ? undefined : "reports-register__mono"}>{recordName(r)}</span>
          <span className="reports-register__meta">{t(`report.register.record_type.${r.recordType}`)}</span>
        </span>
      ),
      csv: (r) => recordName(r),
    },
    {
      id: "generated",
      headerKey: "report.register.column.generated",
      cell: (r) => <time dateTime={generatedAt(r)}>{generatedFormat.format(new Date(generatedAt(r)))}</time>,
      csv: (r) => generatedAt(r),
    },
    {
      id: "error",
      headerKey: "report.register.column.error",
      cell: (r) => (r.errorCode ? t(`report.error.${r.errorCode}`) : ""),
      defaultVisible: false,
      csv: (r) => r.errorCode ?? "",
    },
    {
      id: "download",
      headerKey: "report.register.column.download",
      cell: (r) =>
        r.status === "succeeded" ? (
          <a
            className="reports-register__download"
            href={getReportsRendersFileUrl(r.id)}
            download
            aria-label={t("report.register.download_label", { record: recordName(r) })}
          >
            {t("report.register.download")}
          </a>
        ) : null,
      csv: () => "",
    },
  ];
}
