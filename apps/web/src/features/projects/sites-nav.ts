/**
 * The sites register's entry in the shell's nav registry (PROJECTS-07). Imported for its side
 * effect by the sites route. The item is shown only with `site.view`; the API enforces it.
 */
import { registerNavItem } from "../shell/nav-registry";

registerNavItem({
  id: "sites",
  section: "work-assets",
  to: "/sites",
  icon: "home",
  termKey: "sites.nav.title",
  permission: "site.view",
});
