/**
 * The external users register (PORTAL-07) on DESIGN-03's `RegisterTable`: the tenant's portal users
 * oldest first, Status and "Expiring within" as quick filters, a Project filter, search over email
 * and company, cursor paging and a column chooser. Filters and search live in the URL (see
 * `search.ts`). "Invite external user" shows only with `portal.user.invite`; the API enforces every
 * permission.
 */
import { usePortalUsersList, type PortalUserOut } from "@aip/api-client";
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
import { portalUserColumns } from "./columns";
import { useProjects } from "./format";
import { EXPIRING_WINDOWS, PORTAL_USER_STATUSES, toListParams } from "./search";

export const INVITE = "portal.user.invite";

/** The register's generic labels, worded for external users. */
const PORTAL_TERMS: Readonly<Record<string, string>> = {
  "register.search": "portal.admin.search",
  "register.any": "portal.admin.filter.any",
  "register.clearAll": "portal.admin.filter.clear",
  "register.empty": "portal.admin.filtered_empty",
  "register.loading": "portal.admin.loading",
  "register.error": "portal.admin.error",
  "register.reference": "portal.admin.request_id",
  "register.retry": "portal.admin.retry",
  "register.previous": "portal.admin.previous",
  "register.next": "portal.admin.next",
  "register.pagination": "portal.admin.pagination",
};

/** Project options carry their name, not a term key: `project:<id>` resolves through `names`. */
const PROJECT_OPTION = "project:";

function usePortalUsersPage(query: RegisterQuery): RegisterQueryResult<PortalUserOut> {
  const list = usePortalUsersList(toListParams(query));
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

export interface PortalUsersRegisterProps {
  query: RegisterQuery;
  permissions: readonly string[];
  /** Replace the URL search (the route navigates with `replace: true`). */
  onQueryChange: (next: RegisterQuery) => void;
  /** Enter on a row. */
  onOpenUser: (user: PortalUserOut) => void;
}

export function PortalUsersRegister({ query, permissions, onQueryChange, onOpenUser }: PortalUsersRegisterProps) {
  const columns = useMemo(() => portalUserColumns(), []);
  const { projects, names } = useProjects();
  const filtered = Object.keys(query.filters).length > 0 || Boolean(query.q);

  const translate = useMemo<Translate>(
    () => (key, params) =>
      key.startsWith(PROJECT_OPTION) ? (names.get(key.slice(PROJECT_OPTION.length)) ?? key) : t(PORTAL_TERMS[key] ?? key, params),
    [names],
  );

  const filters = useMemo<readonly RegisterFilter[]>(
    () => [
      {
        id: "status",
        kind: "select",
        labelKey: "portal.admin.filter.status",
        quick: true,
        options: PORTAL_USER_STATUSES.map((value) => ({ value, labelKey: `portal.user.status.${value}` })),
      },
      {
        id: "expiring",
        kind: "select",
        labelKey: "portal.admin.filter.expiring",
        quick: true,
        options: EXPIRING_WINDOWS.map((value) => ({ value, labelKey: `portal.admin.filter.expiring_${value}` })),
      },
      {
        id: "project",
        kind: "select",
        labelKey: "portal.admin.filter.project",
        options: projects.map((p) => ({ value: p.id, labelKey: `${PROJECT_OPTION}${p.id}` })),
      },
    ],
    [projects],
  );

  return (
    <section className="portal-admin" aria-labelledby="portal-users-title">
      <div className="portal-admin__header">
        <h1 id="portal-users-title">{t("portal.admin.title")}</h1>
        {permissions.includes(INVITE) ? (
          <Button asChild>
            <Link to="/admin/portal/users/new">{t("portal.admin.invite")}</Link>
          </Button>
        ) : null}
      </div>
      <p className="portal-admin__meta">{t("portal.admin.intro")}</p>
      <RegisterTable<PortalUserOut>
        id="portal-users"
        captionKey="portal.admin.caption"
        columns={columns}
        filters={filters}
        query={query}
        onQueryChange={onQueryChange}
        useQuery={usePortalUsersPage}
        rowId={(u) => u.id}
        onOpenRow={onOpenUser}
        permissions={permissions}
        translate={translate}
        empty={filtered ? undefined : <p>{t("portal.admin.empty")}</p>}
      />
    </section>
  );
}
