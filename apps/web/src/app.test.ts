import { describe, expect, it } from "vitest";
import { createAppRouter } from "./router";
import { t } from "./terms";

describe("web shell", () => {
  it("resolves the app.title terminology key", () => {
    expect(t("app.title")).toBe("AIP");
  });

  it("registers the index route", () => {
    const router = createAppRouter();
    expect(Object.keys(router.routesByPath)).toContain("/");
  });
});
