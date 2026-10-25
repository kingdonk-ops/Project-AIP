/**
 * Column definitions of the sites register (PROJECTS-07, on DESIGN-03's `RegisterTable`). Sites are
 * tenant-wide; a project references one by `siteId`. The Actions column carries Edit and Delete,
 * shown only with `site.manage` and never for a system site (the hidden per-project site).
 */
import type { SiteOut } from "@aip/api-client";
import { Button, StatusChip, type RegisterColumn } from "@aip/ui";
import { t } from "../shell/t";

export interface SiteRowActions {
  canManage: boolean;
  onEdit: (site: SiteOut) => void;
  onDelete: (site: SiteOut) => void;
}

// ADR 0025: instants are shown in the viewer's own time zone.
const updatedFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function siteColumns(actions: SiteRowActions): RegisterColumn<SiteOut>[] {
  const columns: RegisterColumn<SiteOut>[] = [
    { id: "code", headerKey: "sites.field.code", cell: (s) => s.code, mono: true },
    { id: "name", headerKey: "sites.field.name", cell: (s) => s.name },
    { id: "timezone", headerKey: "sites.field.timezone", cell: (s) => s.timezone ?? "" },
    {
      id: "system",
      headerKey: "sites.field.system",
      cell: (s) => (s.isSystem ? <StatusChip tone="info" icon="shield" label={t("sites.field.system.yes")} /> : ""),
    },
    {
      id: "updated",
      headerKey: "sites.field.updated",
      cell: (s) => <time dateTime={s.updatedAt}>{updatedFormat.format(new Date(s.updatedAt))}</time>,
    },
  ];

  if (actions.canManage) {
    columns.push({
      id: "actions",
      headerKey: "sites.row.actions",
      cell: (s) =>
        s.isSystem ? (
          <span className="sites-register__locked">{t("sites.system.locked")}</span>
        ) : (
          <div className="sites-register__row-actions">
            <Button variant="ghost" onClick={() => actions.onEdit(s)}>
              {t("sites.edit")}
            </Button>
            <Button variant="ghost" onClick={() => actions.onDelete(s)}>
              {t("sites.delete")}
            </Button>
          </div>
        ),
    });
  }

  return columns;
}
