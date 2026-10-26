import { createRoute } from "@tanstack/react-router";
import { ProjectDetail } from "../../../features/projects/ProjectDetail";
import "../../../features/projects/nav";
import { appRoute } from "../../_app";

export const projectDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects/$projectId",
  component: ProjectDetailPage,
});

function ProjectDetailPage() {
  const { projectId } = projectDetailRoute.useParams();
  const { session } = appRoute.useRouteContext();
  return <ProjectDetail projectId={projectId} permissions={session.permissions} />;
}
