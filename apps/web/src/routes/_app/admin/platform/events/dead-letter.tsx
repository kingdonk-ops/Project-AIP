import { decodeRegisterQuery, encodeRegisterQuery } from "@aip/ui";
import { createRoute } from "@tanstack/react-router";
import { useMemo } from "react";
import { OperatorOnly } from "../../../../../features/platform-events/access";
import { DeadLetterPage } from "../../../../../features/platform-events/DeadLetterPage";
import "../../../../../features/platform-events/nav";
import "../../../../../features/platform-events/platform-events.css";
import { deadLetterSpec } from "../../../../../features/platform-events/search";
import { appRoute } from "../../../../_app";

export const platformDeadLetterRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/platform/events/dead-letter",
  // The URL holds the encoded register query; links to the page need no search.
  validateSearch: (search: Record<string, unknown>): Record<string, string> =>
    encodeRegisterQuery(decodeRegisterQuery(search, deadLetterSpec)),
  component: PlatformDeadLetterPage,
});

function PlatformDeadLetterPage() {
  const search = platformDeadLetterRoute.useSearch();
  const navigate = platformDeadLetterRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  const query = useMemo(() => decodeRegisterQuery(search, deadLetterSpec), [search]);
  return (
    <OperatorOnly permissions={session.permissions} titleKey="arch.events.dead_letter.title">
      <DeadLetterPage
        query={query}
        permissions={session.permissions}
        onQueryChange={(next) => void navigate({ search: encodeRegisterQuery(next), replace: true })}
      />
    </OperatorOnly>
  );
}
