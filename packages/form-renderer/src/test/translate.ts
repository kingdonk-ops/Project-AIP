import type { Translate } from "@aip/ui";

/** Test translate (same as packages/ui/src/test/translate.ts): `key`, or `key{a=1}` with params. */
export const tKey: Translate = (key, params) =>
  params
    ? `${key}{${Object.entries(params)
        .map(([k, v]) => `${k}=${v}`)
        .join(",")}}`
    : key;
