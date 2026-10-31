import type { IconName } from "@aip/ui";

/**
 * Rail groups in menu order: My Work (home), then the ADR 0018 job-area groups. A module adds one entry to an
 * existing group and never a new top-level group, so `NavItem.section` only accepts these values. Where each module
 * surfaces is in docs/architecture/module-groups-and-navigation.md.
 */
export const NAV_SECTIONS = ["my-work", "work-assets", "quality", "field", "documents", "insight", "settings"] as const;
/** One of the declared rail groups (ADR 0018). */
export type NavSection = (typeof NAV_SECTIONS)[number];

export interface NavItem {
  id: string;
  section: NavSection;
  /** Route path the item links to. */
  to: string;
  icon: IconName;
  /** Terminology key for the label (`shell.nav.*` or the feature's own key). */
  termKey: string;
  /** Permission the principal needs to see the item. Omit for items every signed-in user sees. */
  permission?: string;
  /** Release flag (ARCH-08) that must be on for the tenant. Omit for items that are always released. */
  flag?: string;
}

const items: NavItem[] = [
  { id: "home", section: "my-work", to: "/", icon: "home", termKey: "shell.nav.home" },
  { id: "projects", section: "work-assets", to: "/projects", icon: "folder", termKey: "shell.nav.projects", permission: "project.view" },
];

/** Features register their entry here (module scope, at import time). Re-registering an id replaces it. */
export function registerNavItem(item: NavItem): void {
  const index = items.findIndex((existing) => existing.id === item.id);
  if (index >= 0) items[index] = item;
  else items.push(item);
}

export function registeredNavItems(): readonly NavItem[] {
  return items;
}

export interface NavGroup {
  section: NavSection;
  items: NavItem[];
}

/**
 * Items the principal may see, grouped by section in site-hierarchy order; empty sections are dropped.
 * A flagged item needs its flag in `enabledFlags` (DESIGN-15): until the flags load, it stays hidden.
 */
export function visibleNavGroups(
  all: readonly NavItem[],
  permissions: readonly string[],
  enabledFlags: readonly string[] = [],
): NavGroup[] {
  const allowed = new Set(permissions);
  const released = new Set(enabledFlags);
  const visible = all.filter(
    (item) =>
      (item.permission === undefined || allowed.has(item.permission)) &&
      (item.flag === undefined || released.has(item.flag)),
  );
  return NAV_SECTIONS.map((section) => ({ section, items: visible.filter((item) => item.section === section) })).filter(
    (group) => group.items.length > 0,
  );
}
