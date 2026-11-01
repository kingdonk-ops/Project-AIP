/**
 * Shared display pieces of the external users pages (PORTAL-07): status and grant-state chips, the
 * next expiry of a user (the earliest live grant), date formatting in the viewer's time zone
 * (ADR 0025) and the tenant's project names for grant rows.
 */
import { useProjectsList, type GrantOut, type PortalUserOut, type ProjectOut } from "@aip/api-client";
import { StatusChip, type IconName, type StatusTone } from "@aip/ui";
import { useMemo } from "react";
import { t } from "../shell/t";
import { EXPIRING_SOON_DAYS } from "./search";

type EffectiveStatus = PortalUserOut["effectiveStatus"];
type GrantState = GrantOut["state"];

const DAY_MS = 24 * 60 * 60 * 1000;
const PROJECT_LOOKUP_LIMIT = 200;

export const USER_STATUS_STYLE: Record<EffectiveStatus, { tone: StatusTone; icon: IconName }> = {
  invited: { tone: "info", icon: "clock" },
  active: { tone: "success", icon: "check" },
  suspended: { tone: "danger", icon: "close" },
  expired: { tone: "warning", icon: "warning" },
};

export const GRANT_STATE_STYLE: Record<GrantState, { tone: StatusTone; icon: IconName }> = {
  live: { tone: "success", icon: "check" },
  expired: { tone: "warning", icon: "warning" },
  revoked: { tone: "neutral", icon: "minus" },
};

export function UserStatusChip({ status }: { status: EffectiveStatus }) {
  const style = USER_STATUS_STYLE[status];
  return <StatusChip tone={style.tone} icon={style.icon} label={t(`portal.user.status.${status}`)} />;
}

export function GrantStateChip({ state }: { state: GrantState }) {
  const style = GRANT_STATE_STYLE[state];
  return <StatusChip tone={style.tone} icon={style.icon} label={t(`portal.grant.state.${state}`)} />;
}

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}

/** The earliest expiry among the user's live grants, or `null` with none. */
export function nextExpiry(user: Pick<PortalUserOut, "grants">): string | null {
  const live = user.grants.filter((g) => g.state === "live").map((g) => g.expiresAt);
  if (live.length === 0) return null;
  return live.reduce((a, b) => (new Date(a) <= new Date(b) ? a : b));
}

/** A live expiry within `EXPIRING_SOON_DAYS` of `now`. */
export function isExpiringSoon(expiresAt: string, now: number = Date.now()): boolean {
  const left = new Date(expiresAt).getTime() - now;
  return left > 0 && left <= EXPIRING_SOON_DAYS * DAY_MS;
}

export function ExpiryCell({ expiresAt }: { expiresAt: string | null }) {
  if (expiresAt === null) return <span className="portal-admin__meta">{t("portal.admin.expiry.none")}</span>;
  return (
    <span className="portal-admin__stack">
      <time dateTime={expiresAt}>{formatDate(expiresAt)}</time>
      {isExpiringSoon(expiresAt) ? <StatusChip tone="warning" icon="clock" label={t("portal.admin.expiry.soon")} /> : null}
    </span>
  );
}

/** The tenant's projects (first 200) by id, for grant rows and the project filter. */
export function useProjects(): { projects: readonly ProjectOut[]; names: ReadonlyMap<string, string> } {
  const list = useProjectsList({ limit: PROJECT_LOOKUP_LIMIT });
  return useMemo(() => {
    const projects = list.data?.status === 200 ? list.data.data.items : [];
    return { projects, names: new Map(projects.map((p) => [p.id, `${p.code} ${p.name}`])) };
  }, [list.data]);
}

/** A grant's project as "CODE Name", else its id while the names load or when it is not listed. */
export function projectLabel(names: ReadonlyMap<string, string>, projectId: string): string {
  return names.get(projectId) ?? projectId;
}

/** The action labels of a grant, in the API's order. */
export function actionLabels(actions: readonly string[]): string {
  return actions.map((a) => t(`portal.grant.action.${a}`)).join(", ");
}
