/**
 * The item-types module's entry in the shell's nav registry (ITEMTYPES-03): one item in the
 * existing Settings group (ADR 0018), shown with `item_type.manage`. The pages themselves need
 * `item_type.view`; the API enforces every permission. Imported for its side effect by the routes.
 */
import { registerNavItem } from "../shell/nav-registry";

registerNavItem({
  id: "content-types",
  section: "settings",
  to: "/admin/content-types",
  icon: "folder",
  termKey: "item_types.nav.title",
  permission: "item_type.manage",
});
