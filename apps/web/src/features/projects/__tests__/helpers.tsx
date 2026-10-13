/**
 * Test helpers for the projects pages: the real router and providers, a fake session, and MSW in
 * front of the generated client. The client calls relative `/api/v1/...` URLs, which Node's fetch
 * cannot resolve, so `resolveRelativeFetch` resolves them against the jsdom origin first.
 */
import type { ProjectOut } from "@aip/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render } from "@testing-library/react";
import axe from "axe-core";
import { setupServer } from "msw/node";
import { createAppRouter } from "../../../router";
import type { Session, SessionPort } from "../../shell/session";
import { SessionPortProvider } from "../../shell/session-context";

export const server = setupServer();

let realFetch: typeof fetch | undefined;

/** Call after `server.listen()`, so relative URLs reach MSW's patched fetch. */
export function resolveRelativeFetch(): void {
  realFetch = globalThis.fetch;
  const patched = realFetch;
  globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
    patched(typeof input === "string" && input.startsWith("/") ? new URL(input, window.location.origin) : input, init);
}

export function restoreFetch(): void {
  if (realFetch) globalThis.fetch = realFetch;
}

export function api(path: string): string {
  return new URL(path, window.location.origin).href;
}

export function session(permissions: readonly string[]): Session {
  return {
    user: { id: "u1", name: "Alice Anderson", email: "alice@kaefer.test" },
    tenant: { slug: "kaefer-demo", name: "Kaefer Demo" },
    permissions,
  };
}

function fakePort(value: Session): SessionPort {
  return {
    getSession: () => Promise.resolve(value),
    startLogin: () => Promise.resolve({ ok: false, reason: "unavailable" }),
    logout: () => Promise.resolve(true),
  };
}

export interface Rendered {
  router: ReturnType<typeof createAppRouter>;
  queryClient: QueryClient;
  container: HTMLElement;
  unmount: () => void;
}

export function renderAt(path: string, permissions: readonly string[]): Rendered {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const port = fakePort(session(permissions));
  const router = createAppRouter({ queryClient, sessionPort: port }, createMemoryHistory({ initialEntries: [path] }));
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionPortProvider port={port}>
        <RouterProvider router={router} />
      </SessionPortProvider>
    </QueryClientProvider>,
  );
  return { router, queryClient, container: view.container, unmount: view.unmount };
}

export function project(overrides: Partial<ProjectOut> & Pick<ProjectOut, "code" | "status">): ProjectOut {
  return {
    id: crypto.randomUUID(),
    name: `Project ${overrides.code}`,
    siteId: null,
    clientCompanyId: null,
    classificationId: null,
    templateId: null,
    region: "ap-southeast-2",
    timezone: "Australia/Perth",
    currency: "AUD",
    closedAt: null,
    syncVersion: 1,
    createdAt: "2026-10-13T00:00:00Z",
    updatedAt: "2026-10-13T01:00:00Z",
    ...overrides,
  };
}

/** Serious and critical axe violations (jsdom has no layout, so contrast is left to Playwright). */
export async function blocking(container: HTMLElement) {
  const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}
