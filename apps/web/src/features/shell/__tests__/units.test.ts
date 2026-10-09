import { describe, expect, it, vi } from "vitest";
import securityHeaders from "../../../../security-headers.json";
import { visibleNavGroups, type NavItem } from "../nav-registry";
import { safeNext } from "../safe-next";
import { t } from "../t";

describe("nav registry", () => {
  const items: NavItem[] = [
    { id: "projects", section: "work", to: "/projects", icon: "folder", termKey: "shell.nav.projects", permission: "project.view" },
    { id: "audit", section: "insight", to: "/audit", icon: "shield", termKey: "shell.nav.audit", permission: "audit.view" },
  ];

  it("renders only the items the principal may see", () => {
    const groups = visibleNavGroups(items, ["project.view"]);
    expect(groups.flatMap((g) => g.items)).toHaveLength(1);
    expect(groups[0]?.items[0]?.id).toBe("projects");
  });

  it("renders nothing when no permission matches", () => {
    expect(visibleNavGroups(items, [])).toEqual([]);
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
