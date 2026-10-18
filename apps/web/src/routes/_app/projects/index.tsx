import { createRoute } from "@tanstack/react-router";
import "../../../features/projects/nav";
import { ProjectsRegister } from "../../../features/projects/ProjectsRegister";
import { projectsQuery, toSearch, validateProjectsSearch } from "../../../features/projects/search";
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
      query={projectsQuery(search)}
      created={search.created}
      permissions={session.permissions}
      // Any change drops the "created" confirmation: it belongs to the arrival from the form.
      onQueryChange={(next) => void navigate({ search: toSearch(next), replace: true })}
      // PROJECTS-07 adds the detail route; until then the path shows the app's not-found page.
      onOpenProject={(project) => void navigate({ href: `/projects/${project.id}` })}
    />
  );
}
