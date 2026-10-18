import { TooltipProvider } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { activeNavItem, documentTitle } from "./brand";
import { Header } from "./Header";
import { NavRail } from "./NavRail";
import { ScopeBar } from "./ScopeBar";
import type { Session } from "./session";
import { useSessionPort } from "./session-context";
import { t } from "./t";
import { registeredNavItems, type NavItem } from "./nav-registry";

export interface AppShellProps {
  session: Session;
  children: ReactNode;
  navItems?: readonly NavItem[] | undefined;
  projectName?: string | undefined;
}

/** The constant frame: header, nav rail, scope bar and the content slot (`main`). */
export function AppShell({ session, children, navItems, projectName }: AppShellProps) {
  const port = useSessionPort();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [navOpen, setNavOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const page = activeNavItem(navItems ?? registeredNavItems(), pathname);
  const pageTitle = page ? t(page.termKey) : undefined;

  // DESIGN-14: `<page> · <Company> AIP`.
  useEffect(() => {
    document.title = documentTitle(session.tenant.name, pageTitle);
  }, [session.tenant.name, pageTitle]);

  // DESIGN-08: the mobile drawer closes on Escape or a backdrop click, and focus goes back to the menu button.
  function dismissNav() {
    setNavOpen(false);
    menuButtonRef.current?.focus();
  }

  useEffect(() => {
    if (!navOpen) return;
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape" && event.key !== "Tab") return;
      // Keys inside another layer (account menu, a dialog or drawer) belong to that layer. Not
      // `defaultPrevented`: Radix prevents Escape when it closes a nav link's tooltip, too.
      if (event.target instanceof Element && event.target.closest('[role="menu"], [role="dialog"]')) return;
      if (event.key === "Tab") {
        trapTab(event);
        return;
      }
      setNavOpen(false);
      menuButtonRef.current?.focus();
    }
    // DESIGN-16: the open drawer is modal. Tab cycles through the menu button and the rail links only.
    function trapTab(event: globalThis.KeyboardEvent) {
      const links = document.getElementById("shell-nav")?.querySelectorAll<HTMLElement>("a[href]") ?? [];
      const stops = [menuButtonRef.current, ...links].filter((stop): stop is HTMLElement => stop !== null);
      if (stops.length === 0) return;
      const current = stops.indexOf(document.activeElement as HTMLElement);
      const step = event.shiftKey ? -1 : 1;
      const next = current === -1 ? 0 : (current + step + stops.length) % stops.length;
      event.preventDefault();
      stops[next]?.focus();
    }
    // Widening past the breakpoint turns the drawer back into the rail, so drop the open state.
    const wide = typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 768px)") : null;
    function onWide(event: MediaQueryListEvent) {
      if (event.matches) setNavOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    wide?.addEventListener("change", onWide);
    // DESIGN-16: the dimmed page does not scroll behind the drawer.
    document.documentElement.classList.add("shell-scroll-locked");
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      wide?.removeEventListener("change", onWide);
      document.documentElement.classList.remove("shell-scroll-locked");
    };
  }, [navOpen]);

  async function signOut(): Promise<boolean> {
    if (!(await port.logout())) return false;
    queryClient.clear();
    await navigate({ to: "/login", search: { signed_out: 1 } });
    return true;
  }

  return (
    <TooltipProvider delayDuration={300}>
      {/* DESIGN-16: while the drawer is open the page behind it is inert (no focus, hidden from the
          accessibility tree); the header stays live because the menu button closes the drawer. */}
      <a className="shell-skip" href="#main" inert={navOpen}>
        {t("shell.skipToContent")}
      </a>
      <div className="shell">
        <Header
          session={session}
          navOpen={navOpen}
          onToggleNav={() => setNavOpen((open) => !open)}
          onSignOut={signOut}
          menuButtonRef={menuButtonRef}
        />
        <NavRail
          permissions={session.permissions}
          items={navItems}
          open={navOpen}
          onNavigate={() => setNavOpen(false)}
        />
        {/* Pointer-only dim layer under the open drawer (shown under 768px); Escape is the keyboard path. */}
        {navOpen ? <div className="shell-backdrop" data-testid="shell-backdrop" aria-hidden="true" onClick={dismissNav} /> : null}
        <div className="shell__body" inert={navOpen}>
          <ScopeBar tenantName={session.tenant.name} projectName={projectName} />
          <main id="main" className="shell__main" tabIndex={-1}>
            {children}
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
