import { TooltipProvider } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { Header } from "./Header";
import { NavRail } from "./NavRail";
import { ScopeBar } from "./ScopeBar";
import type { Session } from "./session";
import { useSessionPort } from "./session-context";
import { t } from "./t";
import type { NavItem } from "./nav-registry";

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

  async function signOut(): Promise<boolean> {
    if (!(await port.logout())) return false;
    queryClient.clear();
    await navigate({ to: "/login", search: { signed_out: 1 } });
    return true;
  }

  return (
    <TooltipProvider delayDuration={300}>
      <a className="shell-skip" href="#main">
        {t("shell.skipToContent")}
      </a>
      <div className="shell">
        <Header session={session} navOpen={navOpen} onToggleNav={() => setNavOpen((open) => !open)} onSignOut={signOut} />
        <NavRail
          permissions={session.permissions}
          items={navItems}
          open={navOpen}
          onNavigate={() => setNavOpen(false)}
        />
        <div className="shell__body">
          <ScopeBar tenantName={session.tenant.name} projectName={projectName} />
          <main id="main" className="shell__main" tabIndex={-1}>
            {children}
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
