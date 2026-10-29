// TESTING-09 unit tests for the walking-skeleton fixtures (no browser, no server).
import { expect, test } from "@playwright/test";
import { runId } from "./run-id";
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

test("the viewer fixture reads E2E_USER_VIEWER and throws when it is missing", () => {
  expect(viewerUser({ E2E_USER_VIEWER: "v@x.test", E2E_PASS_VIEWER: "p" })).toEqual({
    tenant: "kaefer-demo",
    email: "v@x.test",
    password: "p",
  });
  expect(() => viewerUser({ E2E_PASS_VIEWER: "p" })).toThrow("Missing E2E_USER_VIEWER");
});
