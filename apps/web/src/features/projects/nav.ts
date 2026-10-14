/**
 * The projects module's entry in the shell's nav registry (PROJECTS-02). Imported for its side
 * effect by the projects routes. The item is shown only with `project.view`; the API enforces it.
 */
import { registerNavItem } from "../shell/nav-registry";

registerNavItem({
  id: "projects",
  // Work and assets until PROJECTS-03 moves projects to the scope-bar switcher and Settings (ADR 0018).
  section: "work-assets",
  to: "/projects",
  icon: "folder",
  termKey: "projects.nav.title",
  permission: "project.view",
});
