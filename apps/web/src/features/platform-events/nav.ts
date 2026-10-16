/**
 * The platform-events entries in the shell's nav registry (ARCH-09): the catalogue and the
 * dead-letter queue under Settings, shown only with `platform.events.manage`; the API enforces it.
 * They move to the operator console's own origin with OPS-12 (ADR 0017,
 * docs/architecture/module-groups-and-navigation.md). Imported for its side effect by the routes.
 */
import { registerNavItem } from "../shell/nav-registry";
import { EVENTS_MANAGE } from "./access";

registerNavItem({
  id: "platform-events",
  section: "settings",
  to: "/admin/platform/events",
  icon: "info",
  termKey: "arch.events.nav.catalogue",
  permission: EVENTS_MANAGE,
});

registerNavItem({
  id: "platform-dead-letter",
  section: "settings",
  to: "/admin/platform/events/dead-letter",
  icon: "alert",
  termKey: "arch.events.nav.dead_letter",
  permission: EVENTS_MANAGE,
});
