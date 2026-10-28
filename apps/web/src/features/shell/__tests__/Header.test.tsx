import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { createAppRouter } from "../../../router";
import { activeNavItem, BRAND_TOOLTIP_AT, documentTitle } from "../brand";
import type { NavItem } from "../nav-registry";
import type { Session, SessionPort } from "../session";
import { SessionPortProvider } from "../session-context";

// DESIGN-14: the header brand lockup "<Company> AIP" and the document title.

function session(name: string): Session {
  return {
    user: { id: "u1", name: "Alice Anderson", email: "alice@kaefer.test" },
    tenant: { slug: "kaefer-demo", name },
    permissions: ["project.view"],
  };
}

function setup(name: string, path = "/") {
  const port: SessionPort = {
    getSession: () => Promise.resolve(session(name)),
    startLogin: () => Promise.resolve({ ok: true, method: "sso", redirectUrl: "https://kc.example/auth" }),
    logout: () => Promise.resolve(true),
  };
  const queryClient = new QueryClient();
  const router = createAppRouter({ queryClient, sessionPort: port }, createMemoryHistory({ initialEntries: [path] }));
  render(
    <QueryClientProvider client={queryClient}>
      <SessionPortProvider port={port}>
        <RouterProvider router={router} />
      </SessionPortProvider>
    </QueryClientProvider>,
  );
  return router;
}

describe("header brand lockup", () => {
  it("renders one home link named '<Company> AIP, home' with the product word from terms", async () => {
    setup("Kaefer Demo", "/projects");
    const link = await screen.findByRole("link", { name: "Kaefer Demo AIP, home" });
    expect(link.getAttribute("href")).toBe("/");
    expect(link.querySelector(".shell-brand__company")?.textContent).toBe("Kaefer Demo");
    // DESIGN-17 lockup A: the green AIP tag (drawn, not text) with the product word for assistive tech.
    expect(link.querySelector(".aip-lockup__product")?.textContent).toBe("AIP");
    expect(link.querySelector(".aip-lockup__product svg.aip-mark--tag")).not.toBeNull();
    expect(link.querySelector(".shell-brand__company--long")).toBeNull();
  });

  it("a long name gets the truncation class and a tooltip with the full name", async () => {
    const user = userEvent.setup();
    const name = "Kaefer Integrated Services Australia and New Zealand Pty Ltd";
    expect(name.length).toBeGreaterThan(BRAND_TOOLTIP_AT);
    setup(name);
    const link = await screen.findByRole("link", { name: `${name} AIP, home` });
    expect(link.querySelector(".shell-brand__company--long")).not.toBeNull();
    await user.hover(link);
    expect((await screen.findByRole("tooltip")).textContent).toContain(`${name} AIP`);
  });

  it("sets the document title to '<page> · <Company> AIP'", async () => {
    setup("Kaefer Demo", "/projects");
    await screen.findByRole("link", { name: "Kaefer Demo AIP, home" });
    await waitFor(() => expect(document.title).toBe("Projects · Kaefer Demo AIP"));
  });
});

describe("brand helpers", () => {
  const items: NavItem[] = [
    { id: "home", section: "my-work", to: "/", icon: "home", termKey: "shell.nav.home" },
    { id: "projects", section: "work-assets", to: "/projects", icon: "folder", termKey: "shell.nav.projects" },
    { id: "new", section: "work-assets", to: "/projects/new", icon: "folder", termKey: "x" },
  ];

  it("picks the longest matching nav item; '/' matches only itself", () => {
    expect(activeNavItem(items, "/")?.id).toBe("home");
    expect(activeNavItem(items, "/projects")?.id).toBe("projects");
    expect(activeNavItem(items, "/projects/new")?.id).toBe("new");
    expect(activeNavItem(items, "/projects/123")?.id).toBe("projects");
    expect(activeNavItem(items, "/projectsx")).toBeUndefined();
    expect(activeNavItem(items, "/settings")).toBeUndefined();
  });

  it("falls back to the lockup when the page is not in the nav", () => {
    expect(documentTitle("Tenant B")).toBe("Tenant B AIP");
    expect(documentTitle("Tenant B", "Home")).toBe("Home · Tenant B AIP");
  });
});
