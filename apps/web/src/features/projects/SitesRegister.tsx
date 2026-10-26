/**
 * The sites register (PROJECTS-07) on DESIGN-03's `RegisterTable`: search, cursor paging and a
 * column chooser, with create, edit and delete for a user with `site.manage`. Sites are tenant-wide
 * (a project references one by `siteId`); the hidden per-project system site cannot be edited or
 * deleted. Create and edit use a dialog; delete asks for confirmation. The server enforces
 * `site.manage` and answers 409 `SITE_IN_USE` when a site is still referenced.
 */
import {
  getSitesListQueryKey,
  useSitesDelete,
  useSitesList,
  type SiteOut,
} from "@aip/api-client";
import {
  Button,
  confirm,
  RegisterTable,
  toast,
  type RegisterQuery,
  type RegisterQueryResult,
  type Translate,
} from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { t } from "../shell/t";
import { siteColumns } from "./sites-columns";
import { SiteFormDialog } from "./SiteFormDialog";
import { toSitesListParams } from "./sites-search";

/** The register's generic labels, worded for sites (the walking skeleton finds them by name). */
const SITE_TERMS: Readonly<Record<string, string>> = {
  "register.search": "sites.filter.search",
  "register.empty": "sites.empty.filtered",
  "register.loading": "sites.loading",
  "register.error": "sites.error.title",
  "register.reference": "sites.error.request_id",
  "register.retry": "sites.error.retry",
  "register.previous": "sites.page.previous",
  "register.next": "sites.page.next",
  "register.pagination": "sites.page.label",
};

const translate: Translate = (key, params) => t(SITE_TERMS[key] ?? key, params);

function useSitesPage(query: RegisterQuery): RegisterQueryResult<SiteOut> {
  const list = useSitesList(toSitesListParams(query));
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

export interface SitesRegisterProps {
  query: RegisterQuery;
  permissions: readonly string[];
  onQueryChange: (next: RegisterQuery) => void;
}

export function SitesRegister({ query, permissions, onQueryChange }: SitesRegisterProps) {
  const canManage = permissions.includes("site.manage");
  const queryClient = useQueryClient();
  const del = useSitesDelete();
  // `undefined` site + open = create; a set site = edit. Closed when `open` is false.
  const [dialog, setDialog] = useState<{ open: boolean; site?: SiteOut }>({ open: false });

  async function remove(site: SiteOut) {
    const ok = await confirm({
      titleKey: "sites.delete.confirm.title",
      bodyKey: "sites.delete.confirm.body",
      confirmKey: "sites.delete.confirm.submit",
      params: { code: site.code },
      tone: "danger",
    });
    if (!ok) return;
    const response = await del.mutateAsync({ siteId: site.id });
    if (response.status === 204) {
      await queryClient.invalidateQueries({ queryKey: getSitesListQueryKey().slice(0, 1) });
      toast.success("sites.delete.done", { code: site.code });
      return;
    }
    if ((response.status as number) === 409) {
      toast.error("sites.delete.in_use");
      return;
    }
    toast.error("sites.delete.failed");
  }

  const columns = useMemo(
    () => siteColumns({ canManage, onEdit: (site) => setDialog({ open: true, site }), onDelete: (site) => void remove(site) }),
    // `remove` closes over stable hooks; the register re-renders on data change anyway.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canManage],
  );

  return (
    <section className="sites-register" aria-labelledby="sites-title">
      <div className="sites-register__header">
        <h1 id="sites-title">{t("sites.register.title")}</h1>
        {canManage ? <Button onClick={() => setDialog({ open: true })}>{t("sites.register.create")}</Button> : null}
      </div>

      <RegisterTable<SiteOut>
        id="sites"
        captionKey="sites.register.caption"
        columns={columns}
        query={query}
        onQueryChange={onQueryChange}
        useQuery={useSitesPage}
        rowId={(s) => s.id}
        permissions={permissions}
        translate={translate}
        empty={
          query.q ? undefined : (
            <div className="projects-register__empty">
              <p>{t("sites.empty.title")}</p>
              {canManage ? <Button onClick={() => setDialog({ open: true })}>{t("sites.register.create")}</Button> : null}
            </div>
          )
        }
      />

      {canManage && dialog.open ? (
        <SiteFormDialog open site={dialog.site} onOpenChange={(open) => setDialog((d) => ({ ...d, open }))} />
      ) : null}
    </section>
  );
}
