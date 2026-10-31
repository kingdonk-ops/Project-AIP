/**
 * The report engine's entry in the shell's nav registry (REPORTS-04): Insight > Dashboards and
 * reports (ADR 0018). Imported for its side effect by the register route. Shown only with
 * `report.view`; the API enforces it.
 */
import { registerNavItem } from "../shell/nav-registry";

registerNavItem({
  id: "reports",
  section: "insight",
  to: "/reports/register",
  icon: "folder",
  termKey: "report.register.nav",
  permission: "report.view",
});
