/**
 * The release flags page's entry in the shell's nav registry (DESIGN-15): "Release flags" under
 * Settings, shown only with `tenant.flags.manage`; the API enforces it. Imported for its side effect
 * by the route.
 */
import { FLAGS_MANAGE } from "../shell/flags";
import { registerNavItem } from "../shell/nav-registry";

registerNavItem({
  id: "release-flags",
  section: "settings",
  to: "/settings/flags",
  icon: "shield",
  termKey: "shell.flags.nav",
  permission: FLAGS_MANAGE,
});
