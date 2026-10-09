import type { IconName } from "@aip/ui";

/** Section order follows docs/blueprint/03-site-hierarchy.md (Work, Assets, Quality, ..., Insight). */
export const NAV_SECTIONS = ["work", "assets", "quality", "insight"] as const;
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
}

const items: NavItem[] = [
  { id: "home", section: "work", to: "/", icon: "home", termKey: "shell.nav.home" },
  { id: "projects", section: "work", to: "/projects", icon: "folder", termKey: "shell.nav.projects", permission: "project.view" },
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

/** Items the principal may see, grouped by section in site-hierarchy order; empty sections are dropped. */
export function visibleNavGroups(all: readonly NavItem[], permissions: readonly string[]): NavGroup[] {
  const allowed = new Set(permissions);
  const visible = all.filter((item) => item.permission === undefined || allowed.has(item.permission));
  return NAV_SECTIONS.map((section) => ({ section, items: visible.filter((item) => item.section === section) })).filter(
    (group) => group.items.length > 0,
  );
}
