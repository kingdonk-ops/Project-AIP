import { createRoute } from "@tanstack/react-router";
import { ApiHealth } from "../../features/shell/ApiHealth";
import { t } from "../../features/shell/t";
import { appRoute } from "../_app";

export const homeRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  component: HomePage,
});

/** Placeholder Home; "My Work" replaces it later. */
function HomePage() {
  return (
    <>
      <h1>{t("shell.home.title")}</h1>
      <p>{t("shell.home.placeholder")}</p>
      <ApiHealth />
    </>
  );
}
