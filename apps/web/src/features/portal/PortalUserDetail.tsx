/**
 * External user detail (PORTAL-07) on DESIGN-04's `RecordDetail`: the header shows the email,
 * company and effective status; tabs Details (profile and lifecycle dates) and Access (the grants
 * that are not revoked, each with its state and expiry). Actions, each shown only with its
 * permission (the API enforces them too):
 *
 * - renew a live or expired grant and add or revoke a grant (`portal.grant.manage`);
 * - suspend with a reason, and reinstate (`portal.user.suspend`).
 *
 * Renew and reinstate need a fresh second factor: a 401 `STEP_UP_REQUIRED` keeps the pending action,
 * sends the browser to the step-up, and on return offers to run it again (IDENTITY-04). A missing id,
 * or another tenant's (RLS), is a 404 and shows the not-found state.
 */
import {
  getPortalUsersGetQueryKey,
  getPortalUsersListQueryKey,
  portalGrantsCreate,
  portalGrantsRenew,
  portalGrantsRevoke,
  portalUsersReinstate,
  portalUsersSuspend,
  usePortalUsersGet,
  type GrantOut,
  type PortalUserOut,
} from "@aip/api-client";
import {
  Button,
  confirm,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  ErrorState,
  FormField,
  LoadingState,
  RecordDetail,
  toast,
  type RecordStatus,
  type RecordTab,
  type RequestError,
} from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { startStepUp, takePendingStepUp } from "../identity/step-up";
import { t } from "../shell/t";
import { apiError, errorKey } from "./errors";
import { actionLabels, formatDate, GrantStateChip, projectLabel, useProjects, USER_STATUS_STYLE } from "./format";
import { emptyGrant, GrantRow, toGrantIn, type GrantDraft } from "./GrantBuilder";

export const GRANT_MANAGE = "portal.grant.manage";
export const USER_SUSPEND = "portal.user.suspend";
export const DETAIL_STEP_UP_KEY = "portal-user-detail";
const MAX_REASON = 500;

/** An action that needs a step-up, kept across the round trip to Keycloak. */
type Pending = { kind: "renew"; grantId: string } | { kind: "reinstate" };

interface Answer {
  status: number;
  data: unknown;
  headers: Headers;
}

function recordStatus(user: PortalUserOut): RecordStatus {
  const style = USER_STATUS_STYLE[user.effectiveStatus];
  return { tone: style.tone, icon: style.icon, labelKey: `portal.user.status.${user.effectiveStatus}` };
}

export interface PortalUserDetailProps {
  portalUserId: string;
  permissions: readonly string[];
}

export function PortalUserDetail({ portalUserId, permissions }: PortalUserDetailProps) {
  const query = usePortalUsersGet(portalUserId, { query: { retry: false } });
  const { projects, names } = useProjects();
  const queryClient = useQueryClient();
  const [resumed] = useState(() => takePendingStepUp<Pending>(DETAIL_STEP_UP_KEY));
  const [retry, setRetry] = useState<Pending | null>(resumed);
  const [busy, setBusy] = useState(false);
  const [suspendOpen, setSuspendOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  const response = query.data;
  // apiFetch resolves 4xx/5xx as data (with a status): "pending" only before the first answer.
  if (query.isPending || (query.isError && query.isFetching)) {
    return (
      <section className="portal-admin" aria-busy="true" aria-label={t("portal.admin.loading_user")}>
        <LoadingState variant="spinner" translate={t} />
      </section>
    );
  }
  if (query.isError || response === undefined || response.status !== 200) {
    const error: RequestError = response ? { status: response.status, requestId: response.headers.get("x-request-id") } : {};
    return (
      <section className="portal-admin" aria-label={t("portal.admin.title")}>
        <ErrorState error={error} onRetry={() => void query.refetch()} translate={t} />
        <Link to="/admin/portal/users">{t("portal.admin.back")}</Link>
      </section>
    );
  }

  const user = response.data;
  const canManage = permissions.includes(GRANT_MANAGE);
  const canSuspend = permissions.includes(USER_SUSPEND);

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: getPortalUsersGetQueryKey(user.id) });
    await queryClient.invalidateQueries({ queryKey: getPortalUsersListQueryKey().slice(0, 1) });
  }

  /** Run one call; true on success. Handles step-up, 403 and error toasts. */
  async function run(call: () => Promise<Answer>, ok: number, done: string, pending?: Pending): Promise<boolean> {
    setBusy(true);
    try {
      const answer = await call();
      if (answer.status === ok) {
        await refresh();
        toast.success(done);
        return true;
      }
      if (answer.status === 401 && pending && startStepUp(answer, { key: DETAIL_STEP_UP_KEY, state: pending })) return false;
      if (answer.status === 403) {
        toast.error("portal.admin.forbidden");
        return false;
      }
      if (answer.status === 404 || answer.status === 409) await refresh();
      toast.error(answer.status === 404 ? "portal.admin.gone" : errorKey(apiError(answer.data)?.code));
      return false;
    } finally {
      setBusy(false);
    }
  }

  const renew = (grantId: string) =>
    run(() => portalGrantsRenew(user.id, grantId), 200, "portal.admin.renewed", { kind: "renew", grantId });
  const reinstate = () => run(() => portalUsersReinstate(user.id), 200, "portal.admin.reinstated", { kind: "reinstate" });

  async function revoke(grant: GrantOut) {
    const ok = await confirm({
      titleKey: "portal.admin.revoke.title",
      bodyKey: "portal.admin.revoke.body",
      confirmKey: "portal.admin.revoke.submit",
      params: { project: projectLabel(names, grant.projectId) },
      tone: "danger",
    });
    if (ok) await run(() => portalGrantsRevoke(user.id, grant.id), 204, "portal.admin.revoked");
  }

  function retryPending() {
    const pending = retry;
    setRetry(null);
    if (pending?.kind === "renew") void renew(pending.grantId);
    else if (pending?.kind === "reinstate") void reinstate();
  }

  const grantsTab = (
    <div className="portal-admin__grants">
      {user.grants.length === 0 ? (
        <p>{t("portal.admin.grants_none")}</p>
      ) : (
        <table className="portal-admin__table">
          <caption className="portal-admin__caption">{t("portal.admin.grants_caption")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("portal.admin.grant.project")}</th>
              <th scope="col">{t("portal.admin.grant.asset")}</th>
              <th scope="col">{t("portal.admin.grant.actions")}</th>
              <th scope="col">{t("portal.admin.column.state")}</th>
              <th scope="col">{t("portal.admin.column.expires")}</th>
              {canManage ? <th scope="col">{t("portal.admin.column.manage")}</th> : null}
            </tr>
          </thead>
          <tbody>
            {user.grants.map((grant) => {
              const project = projectLabel(names, grant.projectId);
              return (
                <tr key={grant.id} data-grant={grant.id}>
                  <td>{project}</td>
                  <td>{grant.assetId ? <span className="portal-admin__mono">{grant.assetId}</span> : t("portal.admin.grant.asset_whole")}</td>
                  <td>{actionLabels(grant.actions)}</td>
                  <td>
                    <GrantStateChip state={grant.state} />
                  </td>
                  <td>
                    <span className="portal-admin__stack">
                      <time dateTime={grant.expiresAt}>{formatDate(grant.expiresAt)}</time>
                      <span className="portal-admin__meta">{t("portal.admin.grant.period", { days: grant.accessDays })}</span>
                      {grant.renewedAt ? (
                        <span className="portal-admin__meta">{t("portal.admin.grant.renewed_on", { date: formatDate(grant.renewedAt) })}</span>
                      ) : null}
                    </span>
                  </td>
                  {canManage ? (
                    <td className="portal-admin__row-actions">
                      <Button
                        variant="secondary"
                        disabled={busy}
                        aria-label={t("portal.admin.renew_label", { project })}
                        onClick={() => void renew(grant.id)}
                      >
                        {t("portal.admin.renew")}
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={busy}
                        aria-label={t("portal.admin.revoke_label", { project })}
                        onClick={() => void revoke(grant)}
                      >
                        {t("portal.admin.revoke")}
                      </Button>
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {canManage ? (
        <Button variant="secondary" onClick={() => setAddOpen(true)}>
          {t("portal.admin.grant.add")}
        </Button>
      ) : null}
    </div>
  );

  const detailsTab = (
    <dl className="portal-admin__facts">
      <dt>{t("portal.admin.field.email")}</dt>
      <dd>{user.email ?? t("portal.admin.email_unknown")}</dd>
      <dt>{t("portal.admin.field.company")}</dt>
      <dd>{user.companyName}</dd>
      <dt>{t("portal.admin.column.status")}</dt>
      <dd>{t(`portal.user.status.${user.effectiveStatus}`)}</dd>
      <dt>{t("portal.admin.field.invited")}</dt>
      <dd>
        <time dateTime={user.createdAt}>{formatDate(user.createdAt)}</time>
      </dd>
      <dt>{t("portal.admin.column.signed_in")}</dt>
      <dd>{user.firstSignedInAt ? <time dateTime={user.firstSignedInAt}>{formatDate(user.firstSignedInAt)}</time> : t("portal.admin.not_yet")}</dd>
      {user.suspendedAt ? (
        <>
          <dt>{t("portal.admin.field.suspended")}</dt>
          <dd>
            <time dateTime={user.suspendedAt}>{formatDate(user.suspendedAt)}</time>
            {user.suspendedReason ? ` — ${user.suspendedReason}` : null}
          </dd>
        </>
      ) : null}
    </dl>
  );

  const tabs: RecordTab[] = [
    { id: "details", content: detailsTab },
    { id: "access", labelKey: "portal.admin.tab.access", content: grantsTab },
  ];

  const actions =
    canSuspend && user.status === "suspended" ? (
      <Button disabled={busy} onClick={() => void reinstate()}>
        {t("portal.admin.reinstate")}
      </Button>
    ) : canSuspend ? (
      <Button variant="danger" disabled={busy} onClick={() => setSuspendOpen(true)}>
        {t("portal.admin.suspend")}
      </Button>
    ) : undefined;

  return (
    <section className="portal-admin" aria-label={user.email ?? user.companyName}>
      {retry ? (
        <div className="portal-admin__notice" role="status">
          <p>{t("identity.stepUp.retryPrompt")}</p>
          <Button onClick={retryPending}>{t("identity.stepUp.retry")}</Button>
          <Button variant="ghost" onClick={() => setRetry(null)}>
            {t("identity.stepUp.dismiss")}
          </Button>
        </div>
      ) : null}
      <RecordDetail
        id={user.companyName}
        title={user.email ?? user.companyName}
        breadcrumb={<Link to="/admin/portal/users">{t("portal.admin.breadcrumb")}</Link>}
        status={recordStatus(user)}
        tabs={tabs}
        railKey="portal-user"
        {...(actions ? { actions } : {})}
        translate={t}
      />
      {canSuspend ? (
        <SuspendDialog
          open={suspendOpen}
          onOpenChange={setSuspendOpen}
          onSubmit={async (reason) => {
            const ok = await run(() => portalUsersSuspend(user.id, { reason }), 200, "portal.admin.suspended");
            if (ok) setSuspendOpen(false);
          }}
        />
      ) : null}
      {canManage ? (
        <AddGrantDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          projects={projects}
          onSubmit={async (grant) => {
            const ok = await run(() => portalGrantsCreate(user.id, toGrantIn(grant)), 201, "portal.admin.grant_added");
            if (ok) setAddOpen(false);
          }}
        />
      ) : null}
    </section>
  );
}

interface SuspendDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (reason: string) => Promise<void>;
}

function SuspendDialog({ open, onOpenChange, onSubmit }: SuspendDialogProps) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = reason.trim();
    if (trimmed.length === 0 || trimmed.length > MAX_REASON) {
      setError(t("portal.admin.suspend_reason_error", { max: MAX_REASON }));
      return;
    }
    setError(null);
    void onSubmit(trimmed);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("ui.close")}>
        <DialogTitle>{t("portal.admin.suspend_title")}</DialogTitle>
        <DialogDescription>{t("portal.admin.suspend_body")}</DialogDescription>
        <form noValidate onSubmit={submit}>
          <FormField label={t("portal.admin.suspend_reason")} {...(error ? { error } : {})}>
            {(control) => (
              <textarea
                {...control}
                className="portal-admin__textarea"
                rows={3}
                maxLength={MAX_REASON}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            )}
          </FormField>
          <div className="portal-admin__actions">
            <Button type="submit" variant="danger">
              {t("portal.admin.suspend")}
            </Button>
            <DialogClose asChild>
              <Button type="button" variant="ghost">
                {t("portal.admin.cancel")}
              </Button>
            </DialogClose>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface AddGrantDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projects: Parameters<typeof GrantRow>[0]["projects"];
  onSubmit: (grant: GrantDraft) => Promise<void>;
}

function AddGrantDialog({ open, onOpenChange, projects, onSubmit }: AddGrantDialogProps) {
  const [grant, setGrant] = useState<GrantDraft>(() => emptyGrant());
  const [error, setError] = useState<string | undefined>(undefined);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!grant.projectId) {
      setError(t("portal.admin.grant.project_error"));
      return;
    }
    setError(undefined);
    void onSubmit(grant);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("ui.close")}>
        <DialogTitle>{t("portal.admin.grant.add_title")}</DialogTitle>
        <DialogDescription>{t("portal.admin.grants_intro")}</DialogDescription>
        <form noValidate onSubmit={submit}>
          <GrantRow index={0} value={grant} projects={projects} onChange={setGrant} errors={{ project: error }} />
          <div className="portal-admin__actions">
            <Button type="submit">{t("portal.admin.grant.add_submit")}</Button>
            <DialogClose asChild>
              <Button type="button" variant="ghost">
                {t("portal.admin.cancel")}
              </Button>
            </DialogClose>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
