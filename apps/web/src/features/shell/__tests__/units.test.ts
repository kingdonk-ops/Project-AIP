import { describe, expect, it, vi } from "vitest";
import securityHeaders from "../../../../security-headers.json";
import { NAV_SECTIONS, registerNavItem, visibleNavGroups, type NavItem } from "../nav-registry";
import { safeNext } from "../safe-next";
import { t } from "../t";

describe("nav registry", () => {
  const items: NavItem[] = [
    { id: "audit", section: "settings", to: "/audit", icon: "shield", termKey: "shell.nav.audit", permission: "audit.view" },
    { id: "projects", section: "work-assets", to: "/projects", icon: "folder", termKey: "shell.nav.projects", permission: "project.view" },
    { id: "home", section: "my-work", to: "/", icon: "home", termKey: "shell.nav.home" },
  ];

  it("declares the ADR 0018 job-area groups in menu order, after My Work", () => {
    expect(NAV_SECTIONS).toEqual(["my-work", "work-assets", "quality", "field", "documents", "insight", "settings"]);
  });

  it("returns groups in menu order whatever the registration order, dropping empty ones", () => {
    const groups = visibleNavGroups(items, ["project.view", "audit.view"]);
    expect(groups.map((g) => g.section)).toEqual(["my-work", "work-assets", "settings"]);
  });

  it("has a terminology label for every group", () => {
    for (const section of NAV_SECTIONS) expect(t(`shell.nav.section.${section}`)).not.toMatch(/^⟦/);
  });

  it("refuses a top-level group ADR 0018 does not declare", () => {
    const register = (item: NavItem) => item;
    // @ts-expect-error: a module adds one entry to an existing group and never a new top-level group (ADR 0018).
    register({ id: "x", section: "work", to: "/x", icon: "home", termKey: "shell.nav.home" });
    expect(typeof registerNavItem).toBe("function");
  });

  it("renders only the items the principal may see", () => {
    const groups = visibleNavGroups(items, ["project.view"]);
    expect(groups.flatMap((g) => g.items.map((i) => i.id))).toEqual(["home", "projects"]);
  });

  it("renders only ungated items when no permission matches", () => {
    expect(visibleNavGroups(items, []).flatMap((g) => g.items.map((i) => i.id))).toEqual(["home"]);
  });
});

describe("safeNext", () => {
  it.each(["https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)", "", undefined, 5])(
    "rejects %s",
    (value) => {
      expect(safeNext(value)).toBe("/");
    },
  );
  it("keeps same-origin relative paths", () => {
    expect(safeNext("/projects?status=active")).toBe("/projects?status=active");
  });
});

describe("t", () => {
  it("resolves a shell key", () => {
    expect(t("shell.nav.projects")).toBe("Projects");
  });
  it("marks a missing key visibly and warns", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(t("missing.key")).toBe("⟦missing.key⟧");
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe("security headers", () => {
  const csp = securityHeaders.headers["Content-Security-Policy"];
  it("has a strict script policy, no framing and the referrer policy", () => {
    expect(csp).toContain("script-src 'self';");
    expect(csp).not.toMatch(/script-src[^;]*unsafe-inline/);
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("connect-src 'self'");
    expect(securityHeaders.headers["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
  });
});
