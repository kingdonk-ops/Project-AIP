import { createRoute } from "@tanstack/react-router";
import { OperatorOnly } from "../../../../../features/platform-events/access";
import { EventDetailPage } from "../../../../../features/platform-events/EventDetailPage";
import "../../../../../features/platform-events/nav";
import "../../../../../features/platform-events/platform-events.css";
import { appRoute } from "../../../../_app";

export const platformEventDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/platform/events/$eventName",
  component: PlatformEventDetailPage,
});

function PlatformEventDetailPage() {
  const { eventName } = platformEventDetailRoute.useParams();
  const { session } = appRoute.useRouteContext();
  return (
    <OperatorOnly permissions={session.permissions} titleKey="arch.events.catalogue.title">
      <EventDetailPage eventName={eventName} />
    </OperatorOnly>
  );
}
