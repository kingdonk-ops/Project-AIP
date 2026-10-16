/**
 * Platform-operator gate for the event pages (ARCH-09, ADR 0029). Without `platform.events.manage`
 * the page shows the standard 403 state and its children (which hold the API hooks) never mount,
 * so no admin request is made. The API enforces the permission on every call regardless.
 */
import { ErrorState } from "@aip/ui";
import type { ReactNode } from "react";
import { t } from "../shell/t";

export const EVENTS_MANAGE = "platform.events.manage";

export interface OperatorOnlyProps {
  permissions: readonly string[];
  /** Term key of the page title, kept as the heading of the 403 state. */
  titleKey: string;
  children: ReactNode;
}

export function OperatorOnly({ permissions, titleKey, children }: OperatorOnlyProps) {
  if (permissions.includes(EVENTS_MANAGE)) return <>{children}</>;
  return (
    <section className="aip-page" aria-labelledby="platform-events-forbidden">
      <h1 id="platform-events-forbidden">{t(titleKey)}</h1>
      <ErrorState error={{ status: 403 }} onRetry={() => window.location.reload()} translate={t} />
    </section>
  );
}
