import { decodeRegisterQuery, encodeRegisterQuery } from "@aip/ui";
import { createRoute } from "@tanstack/react-router";
import { OperatorOnly } from "../../../../../features/platform-events/access";
import { DeadLetterPage } from "../../../../../features/platform-events/DeadLetterPage";
import "../../../../../features/platform-events/nav";
import "../../../../../features/platform-events/platform-events.css";
import { deadLetterSpec } from "../../../../../features/platform-events/search";
import { appRoute } from "../../../../_app";

export const platformDeadLetterRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/platform/events/dead-letter",
  validateSearch: (search: Record<string, unknown>) => decodeRegisterQuery(search, deadLetterSpec),
  component: PlatformDeadLetterPage,
});

function PlatformDeadLetterPage() {
  const query = platformDeadLetterRoute.useSearch();
  const navigate = platformDeadLetterRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <OperatorOnly permissions={session.permissions} titleKey="arch.events.dead_letter.title">
      <DeadLetterPage
        query={query}
        permissions={session.permissions}
        onQueryChange={(next) => void navigate({ search: encodeRegisterQuery(next) as never, replace: true })}
      />
    </OperatorOnly>
  );
}
