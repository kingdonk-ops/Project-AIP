/**
 * Column definitions of the external users register (PORTAL-07). Nothing sorts (the API lists
 * oldest first). The email links to the user's detail page; "Next expiry" is the earliest live
 * grant, flagged when it ends within 30 days. First sign-in is hidden until the user shows it.
 */
import type { PortalUserOut } from "@aip/api-client";
import type { RegisterColumn } from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { t } from "../shell/t";
import { ExpiryCell, formatDate, nextExpiry, UserStatusChip } from "./format";

export function portalUserColumns(): RegisterColumn<PortalUserOut>[] {
  return [
    {
      id: "email",
      headerKey: "portal.admin.column.email",
      cell: (u) => (
        <Link to="/admin/portal/users/$portalUserId" params={{ portalUserId: u.id }}>
          {u.email ?? t("portal.admin.email_unknown")}
        </Link>
      ),
      csv: (u) => u.email ?? "",
    },
    { id: "company", headerKey: "portal.admin.column.company", cell: (u) => u.companyName, csv: (u) => u.companyName },
    {
      id: "status",
      headerKey: "portal.admin.column.status",
      cell: (u) => <UserStatusChip status={u.effectiveStatus} />,
      csv: (u) => u.effectiveStatus,
    },
    {
      id: "projects",
      headerKey: "portal.admin.column.projects",
      cell: (u) => new Set(u.grants.map((g) => g.projectId)).size,
      csv: (u) => new Set(u.grants.map((g) => g.projectId)).size,
    },
    {
      id: "expiry",
      headerKey: "portal.admin.column.expiry",
      cell: (u) => <ExpiryCell expiresAt={nextExpiry(u)} />,
      csv: (u) => nextExpiry(u) ?? "",
    },
    {
      id: "signedIn",
      headerKey: "portal.admin.column.signed_in",
      cell: (u) => (u.firstSignedInAt ? <time dateTime={u.firstSignedInAt}>{formatDate(u.firstSignedInAt)}</time> : ""),
      defaultVisible: false,
      csv: (u) => u.firstSignedInAt ?? "",
    },
  ];
}
