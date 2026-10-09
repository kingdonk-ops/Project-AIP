import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";
import { createAppRouter } from "../../../router";
import { LoginPage, type LoginSearch } from "../LoginPage";
import type { Session, SessionPort } from "../session";
import { SessionPortProvider } from "../session-context";

const alice: Session = {
  user: { id: "u1", name: "Alice Anderson", email: "alice@kaefer.test" },
  tenant: { slug: "kaefer-demo", name: "Kaefer Demo" },
  permissions: ["project.view"],
};

function fakePort(session: Session | null, overrides: Partial<SessionPort> = {}): SessionPort {
  return {
    getSession: () => Promise.resolve(session),
    startLogin: () => Promise.resolve({ ok: true, method: "sso", redirectUrl: "https://kc.example/auth" }),
    logout: () => Promise.resolve(true),
    ...overrides,
  };
}

function setup(port: SessionPort, path: string) {
  const queryClient = new QueryClient();
  const router = createAppRouter({ queryClient, sessionPort: port }, createMemoryHistory({ initialEntries: [path] }));
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionPortProvider port={port}>
        <RouterProvider router={router} />
      </SessionPortProvider>
    </QueryClientProvider>,
  );
  return { router, queryClient, ...view };
}

async function blocking(container: HTMLElement) {
  // jsdom has no layout engine, so colour contrast is covered by the Playwright axe runs instead.
  const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

describe("route guard", () => {
  it("redirects an unauthenticated visit to /login with the encoded next", async () => {
    const { router } = setup(fakePort(null), "/projects?status=active");
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(router.state.location.href).toBe("/login?next=%2Fprojects%3Fstatus%3Dactive");
  });
});

describe("app shell", () => {
  it("renders landmarks, tenant, only permitted nav items and passes axe", async () => {
    const { container } = setup(fakePort({ ...alice, permissions: [] }), "/");
    expect(await screen.findByRole("banner")).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeTruthy();
    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getAllByText("Kaefer Demo").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Home" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Projects" })).toBeNull();
    expect(await blocking(container)).toEqual([]);
  });

  it("shows Sign out as a submit button inside a POST form, never a link", async () => {
    const user = userEvent.setup();
    setup(fakePort(alice), "/");
    await user.click(await screen.findByRole("button", { name: "Account menu" }));
    const item = await screen.findByRole("menuitem", { name: "Sign out" });
    expect(item.tagName).toBe("BUTTON");
    expect(item.getAttribute("type")).toBe("submit");
    expect(item.closest("form")?.getAttribute("method")).toBe("post");
    expect(screen.getByTestId("user-email").textContent).toBe("alice@kaefer.test");
  });

  it("signs out, clears the cache and lands on /login?signed_out=1", async () => {
    const user = userEvent.setup();
    const logout = vi.fn(() => Promise.resolve(true));
    const { router } = setup(fakePort(alice, { logout }), "/");
    await user.click(await screen.findByRole("button", { name: "Account menu" }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(router.state.location.href).toBe("/login?signed_out=1"));
    expect(logout).toHaveBeenCalledOnce();
  });

  it("stays signed in and says so when sign out fails", async () => {
    const user = userEvent.setup();
    const { router } = setup(fakePort(alice, { logout: () => Promise.resolve(false) }), "/");
    await user.click(await screen.findByRole("button", { name: "Account menu" }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));
    expect(await screen.findByText("Sign out failed. Try again.")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/");
  });
});

describe("login page", () => {
  function renderLogin(port: SessionPort, search: LoginSearch = {}) {
    return render(
      <SessionPortProvider port={port}>
        <LoginPage search={search} />
      </SessionPortProvider>,
    );
  }

  it.each(["sso", "password"] as const)("never shows a password field and redirects for method %s", async (method) => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const startLogin = vi.fn<SessionPort["startLogin"]>(() =>
      Promise.resolve({ ok: true, method, redirectUrl: "https://kc.example/auth" }),
    );
    const { container } = renderLogin(fakePort(null, { startLogin }), { next: "/projects" });
    expect(container.querySelector("input[type=password]")).toBeNull();
    await user.type(screen.getByLabelText("Work email"), "alice@kaefer.test");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://kc.example/auth"));
    expect(startLogin).toHaveBeenCalledWith("alice@kaefer.test", "/projects");
    expect(container.querySelector("input[type=password]")).toBeNull();
    vi.unstubAllGlobals();
  });

  it("replaces an unsafe next with / and shows API error states with term keys", async () => {
    const user = userEvent.setup();
    const startLogin = vi.fn<SessionPort["startLogin"]>(() => Promise.resolve({ ok: false, reason: "rate_limited" }));
    renderLogin(fakePort(null, { startLogin }), { next: "//evil.example" });
    await user.type(screen.getByLabelText("Work email"), "a@b.test");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Too many attempts. Wait a moment and try again.");
    expect(startLogin).toHaveBeenCalledWith("a@b.test", "/");
  });

  it("shows the invited notice and passes axe", async () => {
    const { container } = renderLogin(fakePort(null), { invited: 1 });
    expect(screen.getByText("Sign in to finish setting up your account.")).toBeTruthy();
    expect(await blocking(container)).toEqual([]);
  });
});
