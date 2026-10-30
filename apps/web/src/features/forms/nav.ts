/**
 * The forms module's entry in the shell's nav registry (FORMS-04): Settings > Form templates
 * (ADR 0018: forms surfaces under "Forms and rules" in Settings). Shown only with `form.view`; the
 * API enforces it. Imported for its side effect by the template routes.
 */
import { registerNavItem } from "../shell/nav-registry";

registerNavItem({
  id: "form-templates",
  section: "settings",
  to: "/templates",
  icon: "folder",
  termKey: "forms.templates.nav",
  permission: "form.view",
});
