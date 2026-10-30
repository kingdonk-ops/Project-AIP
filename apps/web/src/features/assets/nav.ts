/**
 * The assets module's entry in the shell's nav registry (ASSETS-03). Imported for its side effect by
 * the assets routes. The item is shown only with `asset.view`; the API enforces it (ADR 0018: the
 * "Work and assets" group).
 */
import { registerNavItem } from "../shell/nav-registry";

registerNavItem({
  id: "assets",
  section: "work-assets",
  to: "/assets",
  icon: "folder",
  termKey: "assets.nav.title",
  permission: "asset.view",
});
