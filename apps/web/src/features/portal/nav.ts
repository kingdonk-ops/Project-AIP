/**
 * The external users register's entry in the shell's nav registry (PORTAL-07): "External users"
 * under Settings (ADR 0018; module-groups doc: Settings > Portal users), shown only with
 * `portal.user.view`; the API enforces it. No release flag: the portal is R1 demo-slice scope, and
 * DESIGN-15 flags gate only deferred modules. Imported for its side effect by the routes.
 */
import { registerNavItem } from "../shell/nav-registry";

export const USER_VIEW = "portal.user.view";

registerNavItem({
  id: "portal-users",
  section: "settings",
  to: "/admin/portal/users",
  icon: "user",
  termKey: "portal.admin.nav",
  permission: USER_VIEW,
});
