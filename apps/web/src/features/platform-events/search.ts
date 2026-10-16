/**
 * URL state of the two registers (ARCH-09), decoded by the routes' `validateSearch` with
 * `decodeRegisterQuery`. Module and version options come from the catalogue itself, so the spec
 * accepts any short value for them and the API ignores what matches nothing.
 */
import type { RegisterSpec } from "@aip/ui";

export const EVENT_STATUSES = ["active", "deprecated"] as const;

export const catalogueSpec: RegisterSpec = {
  filters: [
    { id: "module", kind: "select" },
    { id: "status", kind: "select", options: EVENT_STATUSES.map((value) => ({ value })) },
    { id: "version", kind: "select" },
  ],
  sortable: {},
};

export const deadLetterSpec: RegisterSpec = { filters: [], sortable: {} };
