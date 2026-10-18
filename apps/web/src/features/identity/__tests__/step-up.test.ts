import { describe, expect, it } from "vitest";
import { PENDING_KEY, STEP_UP_START_PATH, startStepUp, stepUpUrlOf, takePendingStepUp, type StepUpDeps } from "../step-up";

function fakeDeps(path = "/settings/users", search = "?tab=invites"): StepUpDeps & {
  store: Map<string, string>;
  assigned: string[];
  clock: { t: number };
} {
  const store = new Map<string, string>();
  const assigned: string[] = [];
  const clock = { t: 1_000_000 };
  return {
    store,
    assigned,
    clock,
    storage: {
      getItem: (k) => store.get(k) ?? null,
      setItem: (k, v) => void store.set(k, v),
      removeItem: (k) => void store.delete(k),
    },
    assign: (url) => void assigned.push(url),
    location: { pathname: path, search },
    now: () => clock.t,
  };
}

const stepUp = {
  status: 401,
  data: {
    detail: {
      code: "STEP_UP_REQUIRED",
      message: "confirm it is you",
      stepUpUrl: `${STEP_UP_START_PATH}?returnTo=/`,
    },
  },
};

describe("step-up", () => {
  it("recognises only the API's STEP_UP_REQUIRED answer", () => {
    expect(stepUpUrlOf(stepUp)).toBe(`${STEP_UP_START_PATH}?returnTo=/`);
    expect(stepUpUrlOf({ status: 401, data: { detail: { code: "SESSION_EXPIRED" } } })).toBeNull();
    expect(stepUpUrlOf({ status: 403, data: stepUp.data })).toBeNull();
    const offSite = { status: 401, data: { detail: { code: "STEP_UP_REQUIRED", stepUpUrl: "https://evil.test/" } } };
    expect(stepUpUrlOf(offSite)).toBeNull();
  });

  it("saves the form and goes to Keycloak, returning to this page", () => {
    const deps = fakeDeps();
    expect(startStepUp(stepUp, { key: "invite", state: { email: "erin@client.test" } }, deps)).toBe(true);
    expect(deps.assigned).toEqual([`${STEP_UP_START_PATH}?returnTo=${encodeURIComponent("/settings/users?tab=invites")}`]);
    expect(JSON.parse(deps.store.get(PENDING_KEY) ?? "{}")).toMatchObject({ key: "invite", path: "/settings/users?tab=invites" });
  });

  it("does nothing for other responses", () => {
    const deps = fakeDeps();
    expect(startStepUp({ status: 201, data: {} }, { key: "invite", state: {} }, deps)).toBe(false);
    expect(deps.assigned).toEqual([]);
  });

  it("hands the saved state back once, on the same page, within 15 minutes", () => {
    const deps = fakeDeps();
    startStepUp(stepUp, { key: "invite", state: { email: "erin@client.test" } }, deps);
    expect(takePendingStepUp("other", deps)).toBeNull();
    expect(takePendingStepUp("invite", deps)).toEqual({ email: "erin@client.test" });
    expect(takePendingStepUp("invite", deps)).toBeNull();

    startStepUp(stepUp, { key: "invite", state: { email: "erin@client.test" } }, deps);
    deps.clock.t += 16 * 60 * 1000;
    expect(takePendingStepUp("invite", deps)).toBeNull();

    startStepUp(stepUp, { key: "invite", state: {} }, deps);
    const elsewhere = { ...deps, location: { pathname: "/projects", search: "" } };
    expect(takePendingStepUp("invite", elsewhere)).toBeNull();
  });
});
