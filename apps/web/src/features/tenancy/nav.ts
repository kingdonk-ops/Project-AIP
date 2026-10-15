/**
 * The tenancy module's entry in the shell's nav registry (ENT-01): "Plan and usage" under Settings,
 * shown only with `tenancy.plan.read`; the API enforces it. Imported for its side effect by the route.
 */
import { registerNavItem } from "../shell/nav-registry";

registerNavItem({
  id: "plan-and-usage",
  section: "settings",
  to: "/settings/billing",
  icon: "info",
  termKey: "tenancy.plan.nav",
  permission: "tenancy.plan.read",
});
