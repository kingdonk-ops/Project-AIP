import type { Translate } from "../register/types";

/** Test translate: returns `key`, or `key{a=1}` with params, so assertions can name the term key. */
export const tKey: Translate = (key, params) =>
  params
    ? `${key}{${Object.entries(params)
        .map(([k, v]) => `${k}=${v}`)
        .join(",")}}`
    : key;
