import { createRoute } from "@tanstack/react-router";
import "../../../features/projects/nav";
import { ProjectCreateForm } from "../../../features/projects/ProjectCreateForm";
import { appRoute } from "../../_app";

export const projectsNewRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects/new",
  component: ProjectsNewPage,
});

function ProjectsNewPage() {
  const navigate = projectsNewRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <ProjectCreateForm
      permissions={session.permissions}
      onCreated={(code) => void navigate({ to: "/projects", search: { created: code } })}
    />
  );
}
