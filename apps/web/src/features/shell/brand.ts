/**
 * The header brand lockup (DESIGN-14): the tenant's display name followed by the product word.
 * The product word is a terminology key (`shell.brand.product`) so it can be renamed without a
 * code change.
 */
import type { NavItem } from "./nav-registry";
import { t } from "./t";

/** Names longer than this get a tooltip with the full name (CSS truncates them with an ellipsis). */
export const BRAND_TOOLTIP_AT = 24;

export function productWord(): string {
  return t("shell.brand.product");
}

/** "Kaefer Demo AIP": the lockup as plain text (tooltips, titles). */
export function brandText(company: string): string {
  return t("shell.brand.title", { company, product: productWord() });
}

/** The nav item for `pathname`: the longest matching `to`, with "/" matching only itself. */
export function activeNavItem(items: readonly NavItem[], pathname: string): NavItem | undefined {
  let best: NavItem | undefined;
  for (const item of items) {
    const matches =
      item.to === "/" ? pathname === "/" : pathname === item.to || pathname.startsWith(`${item.to}/`);
    if (matches && (!best || item.to.length > best.to.length)) best = item;
  }
  return best;
}

/** `<page> · <Company> AIP`, or just the lockup when the page is not in the nav. */
export function documentTitle(company: string, page?: string): string {
  return page === undefined
    ? brandText(company)
    : t("shell.documentTitle", { page, company, product: productWord() });
}
