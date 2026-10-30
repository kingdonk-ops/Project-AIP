/**
 * The shared field-type registry (ITEMTYPES-01) as the admin pages see it. It is read from
 * `@aip/contracts/field-types`, the same JSON the API validates against, so the editor's hints and
 * the preview never drift from the server. Labels come from each entry's `termKey`. Only entries
 * whose `usableIn` contains `attribute` may be used in an item type's attribute list.
 */
import registry from "@aip/contracts/field-types";

export interface FieldTypeEntry {
  key: string;
  termKey: string;
  usableIn: readonly string[];
}

export const FIELD_TYPES: readonly FieldTypeEntry[] = registry.fieldTypes.map(({ key, termKey, usableIn }) => ({
  key,
  termKey,
  usableIn,
}));

/** The field types an item-type attribute may use (`usableIn` contains `attribute`). */
export const ATTRIBUTE_FIELD_TYPES: readonly FieldTypeEntry[] = FIELD_TYPES.filter((f) => f.usableIn.includes("attribute"));

const byKey = new Map(FIELD_TYPES.map((f) => [f.key, f]));
const attributeByKey = new Map(ATTRIBUTE_FIELD_TYPES.map((f) => [f.key, f]));

/** The registry entry for `key`, whatever it is usable in. */
export function fieldType(key: string): FieldTypeEntry | undefined {
  return byKey.get(key);
}

/** The registry entry for `key` when it may be used as an attribute. */
export function attributeFieldType(key: string): FieldTypeEntry | undefined {
  return attributeByKey.get(key);
}
