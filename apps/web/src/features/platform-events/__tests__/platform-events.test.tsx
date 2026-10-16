import type { DeadLetter, EventCatalogue, EventDetail } from "@aip/api-client";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";
import { registeredNavItems, visibleNavGroups } from "../../shell/nav-registry";
import { t } from "../../shell/t";
import { DiscardDialog } from "../DiscardDialog";
import "../nav";

const OPERATOR = ["platform.events.manage"];
const BASE = "/api/v1/admin/platform/events";

const catalogue: EventCatalogue = {
  events: [
    { name: "project.created", version: 1, module: "projects", status: "active", subscribers: ["audit"], published24h: 12, failed24h: 0 },
    { name: "tenant.entitlements_changed", version: 1, module: "tenancy", status: "deprecated", subscribers: [], published24h: 0, failed24h: 2 },
  ],
};

const detail: EventDetail = {
  name: "project.created",
  versions: [
    {
      version: 1,
      status: "active",
      subscribers: ["audit"],
      schema: { title: "ProjectEvent", type: "object", properties: { projectId: { type: "string" } } },
    },
  ],
};

function deadLetter(id: string, overrides: Partial<DeadLetter> = {}): DeadLetter {
  return {
    id,
    eventName: "project.created",
    eventVersion: 1,
    tenantId: "00000000-0000-4000-8000-00000000000a",
    attempts: 10,
    lastError: "TimeoutError: subscriber audit",
    deadLetteredAt: "2026-10-16T02:00:00Z",
    ...overrides,
  };
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

describe("nav entries", () => {
  it("are hidden without platform.events.manage and shown with it", () => {
    const ids = (permissions: string[]) =>
      visibleNavGroups(registeredNavItems(), permissions).flatMap((group) => group.items.map((item) => item.id));
    expect(ids(["project.view"])).not.toContain("platform-events");
    expect(ids(["project.view"])).not.toContain("platform-dead-letter");
    expect(ids(OPERATOR)).toEqual(expect.arrayContaining(["platform-events", "platform-dead-letter"]));
  });
});

describe("access", () => {
  it.each(["/admin/platform/events", "/admin/platform/events/project.created", "/admin/platform/events/dead-letter"])(
    "%s shows the 403 state without the permission and calls no admin API",
    async (path) => {
      let calls = 0;
      server.use(
        http.all(api(`${BASE}*`), () => {
          calls += 1;
          return HttpResponse.json({}, { status: 403 });
        }),
      );
      const { container } = renderAt(path, ["project.view"]);
      expect((await screen.findByRole("alert")).textContent).toContain(t("ui.error.forbidden"));
      expect(calls).toBe(0);
      expect(await blocking(container)).toEqual([]);
    },
  );
});

describe("loading and error states", () => {
  const pages: [string, string][] = [
    ["/admin/platform/events", BASE],
    ["/admin/platform/events/project.created", `${BASE}/project.created`],
    ["/admin/platform/events/dead-letter", `${BASE}/dead-letter`],
  ];

  it.each(pages)("%s has no serious axe violations while loading", async (path, endpoint) => {
    server.use(http.get(api(endpoint), () => new Promise<never>(() => undefined)));
    const { container } = renderAt(path, OPERATOR);
    await screen.findByRole("heading", { level: 1 });
    expect(await blocking(container)).toEqual([]);
  });

  it.each(pages)("%s shows an error state with no serious axe violations when the API fails", async (path, endpoint) => {
    server.use(http.get(api(endpoint), () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    const { container } = renderAt(path, OPERATOR);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(await blocking(container)).toEqual([]);
  });
});

describe("event catalogue", () => {
  it("lists events with their module, status and 24h counts, and filters by module in the URL", async () => {
    const seen: URLSearchParams[] = [];
    server.use(
      http.get(api(BASE), ({ request }) => {
        const params = new URL(request.url).searchParams;
        seen.push(params);
        const module = params.get("module");
        return HttpResponse.json({ events: catalogue.events.filter((e) => !module || e.module === module) });
      }),
    );
    const { container, router } = renderAt("/admin/platform/events", OPERATOR);
    const table = await screen.findByRole("table", { name: t("arch.events.catalogue.caption") });
    const row = await within(table).findByRole("row", { name: /project\.created/ });
    expect(within(row).getByText("projects")).toBeTruthy();
    expect(within(row).getByText(t("arch.events.status.active"))).toBeTruthy();
    expect(within(row).getByText("12")).toBeTruthy();
    expect(within(table).getByRole("row", { name: /tenant\.entitlements_changed/ }).textContent).toContain(
      t("arch.events.status.deprecated"),
    );
    expect(await blocking(container)).toEqual([]);

    fireEvent.change(screen.getByLabelText(t("arch.events.filter.module")), { target: { value: "tenancy" } });
    await waitFor(() => expect(router.state.location.search).toMatchObject({ module: "tenancy" }));
    await waitFor(() => expect(seen.at(-1)?.get("module")).toBe("tenancy"));
    await waitFor(() => expect(within(table).queryByRole("row", { name: /project\.created/ })).toBeNull());
  });
});

describe("event detail", () => {
  it("shows each version's schema and deprecates a version after confirmation", async () => {
    let status: "active" | "deprecated" = "active";
    let deprecations = 0;
    server.use(
      http.get(api(`${BASE}/project.created`), () =>
        HttpResponse.json({ ...detail, versions: detail.versions.map((v) => ({ ...v, status })) }),
      ),
      http.post(api(`${BASE}/project.created/versions/1/deprecate`), () => {
        deprecations += 1;
        status = "deprecated";
        return HttpResponse.json({
          name: "project.created",
          version: 1,
          status: "deprecated",
          deprecatedAt: "2026-10-16T03:00:00Z",
          deprecatedBy: null,
        });
      }),
    );
    const { container } = renderAt("/admin/platform/events/project.created", OPERATOR);
    expect(await screen.findByRole("heading", { name: "project.created", level: 1 })).toBeTruthy();
    const version = await screen.findByRole("region", { name: t("arch.events.detail.version", { version: 1 }) });
    expect(within(version).getByText(/"ProjectEvent"/)).toBeTruthy();
    expect(within(version).getByText("audit")).toBeTruthy();
    expect(await blocking(container)).toEqual([]);

    fireEvent.click(within(version).getByRole("button", { name: t("arch.events.detail.deprecate_version", { version: 1 }) }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: t("arch.events.detail.deprecate_confirm") }));
    await waitFor(() => expect(deprecations).toBe(1));
    expect(await screen.findByText(t("arch.events.detail.deprecated_toast", { name: "project.created", version: 1 }))).toBeTruthy();
    await waitFor(() =>
      expect(within(version).queryByRole("button", { name: t("arch.events.detail.deprecate_version", { version: 1 }) })).toBeNull(),
    );
    expect(within(version).getByText(t("arch.events.status.deprecated"))).toBeTruthy();
  });
});

describe("discard dialog", () => {
  it("enables submit only for a non-blank reason", () => {
    const submitted: string[] = [];
    render(<DiscardDialog open eventId="e1" onOpenChange={() => undefined} onSubmit={(reason) => submitted.push(reason)} />);
    const reason = screen.getByLabelText(t("arch.events.dead_letter.discard_reason"));
    const submit = screen.getByRole("button", { name: t("arch.events.dead_letter.discard_confirm") });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(reason, { target: { value: "   " } });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(reason, { target: { value: "x" } });
    expect((submit as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(submit);
    expect(submitted).toEqual(["x"]);
  });

  it("sends the trimmed reason and caps it at 1000 characters", () => {
    const submitted: string[] = [];
    render(<DiscardDialog open eventId="e1" onOpenChange={() => undefined} onSubmit={(reason) => submitted.push(reason)} />);
    const reason = screen.getByLabelText(t("arch.events.dead_letter.discard_reason"));
    expect(reason.getAttribute("maxlength")).toBe("1000");
    fireEvent.change(reason, { target: { value: "  duplicate delivery  " } });
    fireEvent.click(screen.getByRole("button", { name: t("arch.events.dead_letter.discard_confirm") }));
    expect(submitted).toEqual(["duplicate delivery"]);
  });
});

describe("dead-letter queue", () => {
  function listing(items: () => DeadLetter[], calls: { list: number }) {
    return http.get(api(`${BASE}/dead-letter`), () => {
      calls.list += 1;
      return HttpResponse.json({ items: items(), nextAfter: null });
    });
  }

  it("retries a dead letter, toasts and refetches", async () => {
    let rows = [deadLetter("e1"), deadLetter("e2")];
    const calls = { list: 0 };
    server.use(
      listing(() => rows, calls),
      http.post(api(`${BASE}/dead-letter/e1/retry`), () => {
        rows = rows.filter((r) => r.id !== "e1");
        return HttpResponse.json({ id: "e1", eventName: "project.created", eventVersion: 1, action: "retried" });
      }),
    );
    const { container } = renderAt("/admin/platform/events/dead-letter", OPERATOR);
    const table = await screen.findByRole("table", { name: t("arch.events.dead_letter.caption") });
    const row = await within(table).findByRole("row", { name: /e1/ });
    expect(within(row).getByText("TimeoutError: subscriber audit")).toBeTruthy();
    expect(await blocking(container)).toEqual([]);

    fireEvent.click(within(row).getByRole("button", { name: t("arch.events.dead_letter.retry_row", { id: "e1" }) }));
    expect(await screen.findByText(t("arch.events.dead_letter.retried_toast"))).toBeTruthy();
    await waitFor(() => expect(within(table).queryByRole("row", { name: /e1/ })).toBeNull());
    expect(calls.list).toBeGreaterThanOrEqual(2);
  });

  it("says another operator already handled it when retry returns 404, and refetches", async () => {
    const calls = { list: 0 };
    server.use(
      listing(() => [deadLetter("e1")], calls),
      http.post(api(`${BASE}/dead-letter/e1/retry`), () => HttpResponse.json({ detail: "not found" }, { status: 404 })),
    );
    renderAt("/admin/platform/events/dead-letter", OPERATOR);
    const row = await screen.findByRole("row", { name: /e1/ });
    const before = calls.list;
    fireEvent.click(within(row).getByRole("button", { name: t("arch.events.dead_letter.retry_row", { id: "e1" }) }));
    expect(await screen.findByText(t("arch.events.dead_letter.already_handled"))).toBeTruthy();
    await waitFor(() => expect(calls.list).toBeGreaterThan(before));
  });

  it("discards with a reason through the dialog", async () => {
    let rows = [deadLetter("e1")];
    const bodies: unknown[] = [];
    server.use(
      listing(() => rows, { list: 0 }),
      http.post(api(`${BASE}/dead-letter/e1/discard`), async ({ request }) => {
        bodies.push(await request.json());
        rows = [];
        return HttpResponse.json({ id: "e1", eventName: "project.created", eventVersion: 1, action: "discarded" });
      }),
    );
    renderAt("/admin/platform/events/dead-letter", OPERATOR);
    const row = await screen.findByRole("row", { name: /e1/ });
    fireEvent.click(within(row).getByRole("button", { name: t("arch.events.dead_letter.discard_row", { id: "e1" }) }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(t("arch.events.dead_letter.discard_reason")), {
      target: { value: "Bad payload, raised INC-42" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: t("arch.events.dead_letter.discard_confirm") }));
    await waitFor(() => expect(bodies).toEqual([{ reason: "Bad payload, raised INC-42" }]));
    expect(await screen.findByText(t("arch.events.dead_letter.discarded_toast"))).toBeTruthy();
    expect(await screen.findByText(t("register.empty"))).toBeTruthy();
  });

  it("retries the selected rows and reports how many succeeded", async () => {
    let rows = [deadLetter("e1"), deadLetter("e2")];
    server.use(
      listing(() => rows, { list: 0 }),
      http.post(api(`${BASE}/dead-letter/e1/retry`), () => {
        rows = rows.filter((r) => r.id !== "e1");
        return HttpResponse.json({ id: "e1", eventName: "project.created", eventVersion: 1, action: "retried" });
      }),
      http.post(api(`${BASE}/dead-letter/e2/retry`), () => HttpResponse.json({ detail: "not found" }, { status: 404 })),
    );
    renderAt("/admin/platform/events/dead-letter", OPERATOR);
    await screen.findByRole("row", { name: /e2/ });
    await act(async () => {
      fireEvent.click(screen.getByRole("checkbox", { name: t("register.selectPage") }));
    });
    fireEvent.click(await screen.findByRole("button", { name: t("arch.events.dead_letter.retry_selected") }));
    expect(await screen.findByText(t("arch.events.dead_letter.retried_some", { done: 1, total: 2 }))).toBeTruthy();
  });

  it("ignores a second press of Retry selected while the first run is going", async () => {
    let retries = 0;
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => (release = resolve));
    server.use(
      listing(() => [deadLetter("e1")], { list: 0 }),
      http.post(api(`${BASE}/dead-letter/e1/retry`), async () => {
        retries += 1;
        await gate;
        return HttpResponse.json({ id: "e1", eventName: "project.created", eventVersion: 1, action: "retried" });
      }),
    );
    renderAt("/admin/platform/events/dead-letter", OPERATOR);
    await screen.findByRole("row", { name: /e1/ });
    await act(async () => {
      fireEvent.click(screen.getByRole("checkbox", { name: t("register.selectPage") }));
    });
    const bulk = await screen.findByRole("button", { name: t("arch.events.dead_letter.retry_selected") });
    fireEvent.click(bulk);
    fireEvent.click(bulk);
    release();
    expect(await screen.findByText(t("arch.events.dead_letter.retried_some", { done: 1, total: 1 }))).toBeTruthy();
    expect(retries).toBe(1);
  });

  it("puts focus on the page heading after the acted-on row disappears", async () => {
    let rows = [deadLetter("e1")];
    server.use(
      listing(() => rows, { list: 0 }),
      http.post(api(`${BASE}/dead-letter/e1/retry`), () => {
        rows = [];
        return HttpResponse.json({ id: "e1", eventName: "project.created", eventVersion: 1, action: "retried" });
      }),
    );
    renderAt("/admin/platform/events/dead-letter", OPERATOR);
    const row = await screen.findByRole("row", { name: /e1/ });
    fireEvent.click(within(row).getByRole("button", { name: t("arch.events.dead_letter.retry_row", { id: "e1" }) }));
    const heading = screen.getByRole("heading", { name: t("arch.events.dead_letter.title"), level: 1 });
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });

  it("pages forward with the API's nextAfter as the after parameter", async () => {
    const afters: (string | null)[] = [];
    server.use(
      http.get(api(`${BASE}/dead-letter`), ({ request }) => {
        const after = new URL(request.url).searchParams.get("after");
        afters.push(after);
        return after
          ? HttpResponse.json({ items: [deadLetter("e3")], nextAfter: null })
          : HttpResponse.json({ items: [deadLetter("e1"), deadLetter("e2")], nextAfter: "e2" });
      }),
    );
    renderAt("/admin/platform/events/dead-letter", OPERATOR);
    await screen.findByRole("row", { name: /e2/ });
    fireEvent.click(screen.getByRole("button", { name: t("register.next") }));
    expect(await screen.findByRole("row", { name: /e3/ })).toBeTruthy();
    expect(afters).toEqual([null, "e2"]);
  });
});
