// TESTING-09 unit tests for the walking-skeleton fixtures (no browser, no server).
import { expect, test } from "@playwright/test";
import { runId } from "./run-id";
import { keycloakAdminConfig } from "./keycloak-admin";
import { tenantUsers, viewerUser } from "./tenants";

test("runId is <run id>-<attempt> on GitHub Actions", () => {
  expect(runId({ GITHUB_RUN_ID: "123", GITHUB_RUN_ATTEMPT: "2" })).toBe("123-2");
});

test("runId is a 13-digit millisecond timestamp locally", () => {
  expect(runId({})).toMatch(/^\d{13}$/);
  expect(runId({}, () => 1_700_000_000_000)).toBe("1700000000000");
});

test("the tenants fixture throws when a user is missing instead of skipping", () => {
  const complete = { E2E_USER_A: "a@x.test", E2E_PASS_A: "p", E2E_USER_B: "b@y.test", E2E_PASS_B: "q" };
  expect(tenantUsers(complete).b).toEqual({ tenant: "tenant-b", email: "b@y.test", password: "q" });
  const { E2E_USER_B: _omitted, ...withoutB } = complete;
  expect(() => tenantUsers(withoutB)).toThrow("Missing E2E_USER_B");
  expect(() => tenantUsers({ ...complete, E2E_PASS_A: "  " })).toThrow("Missing E2E_PASS_A");
});

test("the viewer fixture is a kaefer-demo user and throws when missing (TESTING-12)", () => {
  const env = { E2E_USER_VIEWER: "v@x.test", E2E_PASS_VIEWER: "p" };
  expect(viewerUser(env)).toEqual({ tenant: "kaefer-demo", email: "v@x.test", password: "p" });
  expect(() => viewerUser({ E2E_USER_VIEWER: "v@x.test" })).toThrow("Missing E2E_PASS_VIEWER");
});

test("the Keycloak admin fixture throws when a variable is missing (TESTING-12)", () => {
  const env = { E2E_KEYCLOAK_URL: "http://kc.test", E2E_KEYCLOAK_ADMIN: "admin", E2E_KEYCLOAK_ADMIN_PASSWORD: "p" };
  expect(keycloakAdminConfig(env)).toEqual({ url: "http://kc.test", username: "admin", password: "p" });
  expect(() => keycloakAdminConfig({ ...env, E2E_KEYCLOAK_URL: "" })).toThrow("Missing E2E_KEYCLOAK_URL");
});
