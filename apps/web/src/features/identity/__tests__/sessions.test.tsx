import { onSessionExpired, withCsrf } from "@aip/api-client";
import { identityGetMe } from "@aip/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
// jsdom will not store a `__Host-` cookie on its http test origin, so the cookie is stubbed.
function setCookie(value: string): void {
  Object.defineProperty(document, "cookie", { configurable: true, get: () => value });
}

afterEach(() => {
  server.resetHandlers();
  setCookie("");
});
afterAll(() => {
  restoreFetch();
  server.close();
});

const sessions = [
  {
    id: "s-current",
    current: true,
    audience: "app",
    aal: 2,
    ip: "203.0.113.7",
    userAgent: "Firefox on Linux",
    createdAt: "2026-10-13T00:00:00Z",
    lastSeenAt: "2026-10-13T01:00:00Z",
  },
  {
    id: "s-other",
    current: false,
    audience: "app",
    aal: 1,
    ip: "198.51.100.9",
    userAgent: "Safari on iPad",
    createdAt: "2026-10-12T00:00:00Z",
    lastSeenAt: "2026-10-12T05:00:00Z",
  },
];

describe("CSRF-aware fetch", () => {
  it("sends the CSRF cookie as a header on unsafe methods only", () => {
    setCookie("other=1; __Host-aip_csrf=tok123");
    expect(new Headers(withCsrf({ method: "DELETE" }).headers).get("X-CSRF-Token")).toBe("tok123");
    expect(new Headers(withCsrf({ method: "GET" }).headers).get("X-CSRF-Token")).toBeNull();
    expect(withCsrf({}).credentials).toBe("same-origin");
  });

  it("signals an expired session", async () => {
    server.use(
      http.get(api("/api/v1/me"), () =>
        HttpResponse.json({ detail: { code: "SESSION_EXPIRED", message: "ended" } }, { status: 401 }),
      ),
    );
    let signalled = 0;
    const off = onSessionExpired(() => {
      signalled += 1;
    });
    const response = await identityGetMe();
    off();
    expect(response.status).toBe(401);
    expect(signalled).toBe(1);
  });
});

describe("active sessions page", () => {
  it("lists sessions, marks this device and signs another one out with the CSRF token", async () => {
    setCookie("other=1; __Host-aip_csrf=tok123");
    let list = sessions;
    const revoked: { id: string; token: string | null }[] = [];
    server.use(
      http.get(api("/api/v1/me/sessions"), () => HttpResponse.json({ items: list })),
      http.delete(api("/api/v1/me/sessions/:id"), ({ params, request }) => {
        revoked.push({ id: String(params.id), token: request.headers.get("X-CSRF-Token") });
        list = sessions.filter((s) => s.id !== params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { container } = renderAt("/settings/profile/sessions", []);

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText(/This device/)).toBeTruthy();
    expect(within(rows[1]!).getByText("198.51.100.9")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Sign out the session on Safari on iPad" }));
    await waitFor(() => expect(revoked).toEqual([{ id: "s-other", token: "tok123" }]));
    await waitFor(() => expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2));
    expect(await blocking(container)).toEqual([]);
  });

  it("shows an error when the list cannot load", async () => {
    server.use(http.get(api("/api/v1/me/sessions"), () => HttpResponse.json({}, { status: 500 })));
    renderAt("/settings/profile/sessions", []);
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
