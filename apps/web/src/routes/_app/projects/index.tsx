import { createRoute } from "@tanstack/react-router";
import "../../../features/projects/nav";
import { ProjectsRegister } from "../../../features/projects/ProjectsRegister";
import { validateProjectsSearch } from "../../../features/projects/search";
import { appRoute } from "../../_app";

export const projectsIndexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects",
  validateSearch: validateProjectsSearch,
  component: ProjectsIndexPage,
});

function ProjectsIndexPage() {
  const search = projectsIndexRoute.useSearch();
  const navigate = projectsIndexRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <ProjectsRegister
      search={search}
      permissions={session.permissions}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
    />
  );
}
