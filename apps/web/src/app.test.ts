import { getPlatformHealthQueryKey, getPlatformHealthUrl } from "@aip/api-client";
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { httpSessionPort } from "./features/shell/session";
import { createAppRouter } from "./router";
import { t } from "./terms";

const makeRouter = () => createAppRouter({ queryClient: new QueryClient(), sessionPort: httpSessionPort });

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

  it("registers the home, projects and login routes", () => {
    const router = makeRouter();
    expect(Object.keys(router.routesByPath)).toEqual(expect.arrayContaining(["/", "/projects", "/login"]));
  });

  it("registers the dev-only UI fixture route outside production", () => {
    const router = makeRouter();
    expect(Object.keys(router.routesByPath)).toContain("/__fixtures/ui");
  });
});
