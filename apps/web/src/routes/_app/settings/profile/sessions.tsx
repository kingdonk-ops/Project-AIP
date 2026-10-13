import { createRoute } from "@tanstack/react-router";
import { ActiveSessionsPage } from "../../../../features/identity/ActiveSessionsPage";
import { appRoute } from "../../../_app";

export const sessionsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/settings/profile/sessions",
  component: ActiveSessionsPage,
});
