import { getPlatformHealthQueryKey, getPlatformHealthUrl } from "@aip/api-client";
import { describe, expect, it } from "vitest";
import { createAppRouter } from "./router";
import { t } from "./terms";

describe("web shell", () => {
  it("resolves the app.title terminology key", () => {
    expect(t("app.title")).toBe("AIP");
  });

  it("has en-AU defaults for the API health keys", () => {
    expect(t("health.label")).toBe("API status");
    expect(t("health.unavailable")).toBe("Unavailable");
  });

  it("builds the health request from the generated client", () => {
    expect(getPlatformHealthUrl()).toBe("/api/v1/health");
    expect(getPlatformHealthQueryKey()).toEqual(["/api/v1/health"]);
  });

  it("registers the index route", () => {
    const router = createAppRouter();
    expect(Object.keys(router.routesByPath)).toContain("/");
  });
});
