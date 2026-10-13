/**
 * The projects module's entry in the shell's nav registry (PROJECTS-02). Imported for its side
 * effect by the projects routes. The item is shown only with `project.view`; the API enforces it.
 */
import { registerNavItem } from "../shell/nav-registry";

registerNavItem({
  id: "projects",
  section: "work",
  to: "/projects",
  icon: "folder",
  termKey: "projects.nav.title",
  permission: "project.view",
});
