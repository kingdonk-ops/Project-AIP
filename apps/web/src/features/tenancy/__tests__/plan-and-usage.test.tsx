import type { PlanAndUsage } from "@aip/api-client";
import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";

const READ = ["tenancy.plan.read"];

const professional: PlanAndUsage = {
  plan: "professional",
  planVersion: 1,
  term: "annual",
  status: "active",
  renewalDate: "2027-06-30",
  contractRef: "C-1001",
  usagePeriod: "2026-10-01",
  features: [
    { key: "feature.api", enabled: true, source: "plan" },
    { key: "feature.sso", enabled: false, source: "plan" },
  ],
  limits: [
    { key: "limit.seats.full", limit: 5, used: 3, action: "OVERAGE", source: "plan" },
    { key: "limit.seats.portal", limit: 20, used: 7, action: "OVERAGE", source: "plan" },
    { key: "limit.storage_gb", limit: 250, used: 12.5, action: "BLOCK", source: "plan" },
    { key: "limit.projects", limit: null, used: null, action: "OVERAGE", source: "override" },
  ],
  dbEstimate: { bytes: 1024, method: "row-bytes-v1", capturedAt: "2026-10-15T02:00:00Z" },
};

function planIs(body: PlanAndUsage | null, status = 200) {
  return http.get(api("/api/v1/settings/plan-and-usage"), () => HttpResponse.json(body, { status }));
}

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

describe("plan and usage page", () => {
  it("shows the plan, renewal date, contract and seats used against each limit", async () => {
    server.use(planIs(professional));
    const { container } = renderAt("/settings/billing", READ);

    expect(await screen.findByRole("heading", { name: "Plan and usage", level: 1 })).toBeTruthy();
    const summary = await screen.findByRole("region", { name: "Subscription" });
    expect(within(summary).getByText("Professional")).toBeTruthy();
    expect(within(summary).getByText("Annual")).toBeTruthy();
    expect(within(summary).getByText("30 June 2027")).toBeTruthy();
    expect(within(summary).getByText("C-1001")).toBeTruthy();

    const usage = screen.getByRole("table", { name: "Usage against limits" });
    const seats = within(usage).getByRole("row", { name: /Full users/ });
    expect(within(seats).getByText("3")).toBeTruthy();
    expect(within(seats).getByText("5")).toBeTruthy();
    expect(within(usage).getByRole("row", { name: /Reviewer seats/ })).toBeTruthy();
    expect(within(usage).getByRole("row", { name: /Active projects/ }).textContent).toContain("Unlimited");
    expect(screen.getByText(/Usage measured for October 2026/)).toBeTruthy();

    const features = screen.getByRole("table", { name: "Features" });
    expect(within(features).getByRole("row", { name: /Single sign-on/ }).textContent).toContain("Not included");
    expect(await blocking(container)).toEqual([]);
  });

  it("offers no plan change, invoice or payment control", async () => {
    server.use(planIs(professional));
    renderAt("/settings/billing", READ);
    await screen.findByRole("region", { name: "Subscription" });
    const page = within(screen.getByRole("region", { name: "Plan and usage" }));
    expect(page.queryByRole("button")).toBeNull();
    expect(page.queryByRole("link")).toBeNull();
    expect(page.queryByText(/change plan|invoice|payment|upgrade/i)).toBeNull();
  });

  it("says so when the tenant has no subscription", async () => {
    server.use(
      planIs({
        ...professional,
        plan: null,
        planVersion: null,
        term: null,
        status: null,
        renewalDate: null,
        contractRef: null,
        usagePeriod: null,
        dbEstimate: null,
      }),
    );
    renderAt("/settings/billing", READ);
    expect(await screen.findByText(/no active subscription/)).toBeTruthy();
    expect(screen.getByText("Usage has not been measured yet.")).toBeTruthy();
  });

  it("shows an error when the API refuses", async () => {
    server.use(planIs(null, 403));
    renderAt("/settings/billing", READ);
    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
  });
});
