import { createRoute } from "@tanstack/react-router";
import { t } from "../../features/shell/t";
import { appRoute } from "../_app";

export const projectsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects",
  validateSearch: (search: Record<string, unknown>): { status?: string } =>
    typeof search.status === "string" ? { status: search.status } : {},
  component: ProjectsPage,
});

/** Placeholder so the nav item has a destination; PROJECTS-02 replaces it with the register. */
function ProjectsPage() {
  return (
    <>
      <h1>{t("shell.projects.title")}</h1>
      <p>{t("shell.projects.placeholder")}</p>
    </>
  );
}
