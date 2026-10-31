import { createRoute } from "@tanstack/react-router";
import { FlagsPage } from "../../../features/flags/FlagsPage";
import "../../../features/flags/flags.css";
import "../../../features/flags/nav";
import { appRoute } from "../../_app";

export const flagsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/settings/flags",
  component: FlagsRoutePage,
});

function FlagsRoutePage() {
  const { session } = appRoute.useRouteContext();
  return <FlagsPage permissions={session.permissions} />;
}
