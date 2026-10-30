/**
 * The register's generic labels worded for assets (ASSETS-03), the way `features/projects` maps its
 * terms. Item type filter options carry `itemType:<id>` as their label key: item type names are data,
 * not terminology, so `assetsTranslate` looks them up in the names it is given.
 */
import type { Translate } from "@aip/ui";
import { t } from "../shell/t";

const ASSET_TERMS: Readonly<Record<string, string>> = {
  "register.search": "assets.filter.search",
  "register.clearAll": "assets.filter.clear",
  "register.empty": "assets.register.filtered_empty",
  "register.loading": "assets.register.loading",
  "register.error": "assets.register.error",
  "register.reference": "assets.register.request_id",
  "register.retry": "assets.register.retry",
  "register.previous": "assets.register.previous",
  "register.next": "assets.register.next",
  "register.pagination": "assets.register.pagination",
};

export const ITEM_TYPE_OPTION_PREFIX = "itemType:";

export function assetsTranslate(itemTypeNames: ReadonlyMap<string, string>): Translate {
  return (key, params) => {
    if (key.startsWith(ITEM_TYPE_OPTION_PREFIX)) {
      const id = key.slice(ITEM_TYPE_OPTION_PREFIX.length);
      return itemTypeNames.get(id) ?? id;
    }
    return t(ASSET_TERMS[key] ?? key, params);
  };
}

const KNOWN_CODES: ReadonlySet<string> = new Set([
  "PATH_CYCLE",
  "ASSET_TREE_TOO_DEEP",
  "PARENT_NOT_FOUND",
  "VERSION_CONFLICT",
  "TAG_NUMBER_IN_USE",
  "ITEM_TYPE_NOT_PUBLISHED",
  "ATTRIBUTES_INVALID",
  "ATTRIBUTES_WITHOUT_TYPE",
]);

/** The message for an API error `code` (`assets.error.<code>`), or the generic save failure. */
export function errorMessage(code: string | undefined, fallback = "assets.form.save_failed"): string {
  return code && KNOWN_CODES.has(code) ? t(`assets.error.${code}`) : t(fallback);
}

/** The `code` of an API error body (`{code, ...}`), if any. */
export function errorCode(data: unknown): string | undefined {
  if (typeof data !== "object" || data === null) return undefined;
  const code = (data as { code?: unknown }).code;
  return typeof code === "string" ? code : undefined;
}

/** "Reference: <id>" appended to a message when the response carries a request id. */
export function withReference(message: string, headers: Headers | undefined): string {
  const id = headers?.get("x-request-id");
  return id ? `${message} ${t("assets.error.request_id", { id })}` : message;
}
