import { describe, expect, it } from "vitest";
import { decodeRegisterQuery, encodeRegisterQuery, type RegisterSpec } from "./url-state";

const spec: RegisterSpec = {
  filters: [
    { id: "status", kind: "multi", options: [{ value: "active" }, { value: "draft" }, { value: "archived" }] },
    { id: "site", kind: "select" },
    { id: "due", kind: "date-range" },
  ],
  sortable: { code: ["asc", "desc"], updated_at: ["desc"] },
  columns: ["code", "name", "region"],
};

describe("register URL state", () => {
  it("round-trips filters, sort, limit and columns", () => {
    const query = {
      filters: { status: ["active", "draft"], due: ["2026-01-01", "2026-02-01"] },
      sort: { id: "code", dir: "desc" as const },
      limit: 100,
      q: "ichthys",
      cursor: "abc",
      columns: ["code", "name"],
    };
    expect(decodeRegisterQuery(encodeRegisterQuery(query), spec)).toEqual(query);
    const simple = { filters: { status: ["active", "draft"] }, sort: { id: "code", dir: "desc" as const }, limit: 50 };
    expect(decodeRegisterQuery(encodeRegisterQuery(simple), spec)).toEqual(simple);
    expect(encodeRegisterQuery(simple)).toEqual({ status: "active,draft", sort: "-code" });
  });

  it("drops invalid values instead of throwing", () => {
    expect(decodeRegisterQuery("?limit=9999&sort=__proto__", spec)).toEqual({ filters: {}, limit: 50 });
    const odd = decodeRegisterQuery(
      "?status=active,bogus&sort=updated_at&due=yesterday..&cols=nope,code&unknown=1&constructor=x",
      spec,
    );
    expect(odd).toEqual({ filters: { status: ["active"] }, limit: 50, columns: ["code"] });
  });

  it("accepts a router search object", () => {
    expect(decodeRegisterQuery({ site: "S1", limit: 25, sort: "-updated_at" }, spec)).toEqual({
      filters: { site: "S1" },
      limit: 25,
      sort: { id: "updated_at", dir: "desc" },
    });
  });
});
