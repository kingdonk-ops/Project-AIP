import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Icon,
} from "@aip/ui";
import { useState } from "react";
import type { Session } from "./session";
import { t } from "./t";

export interface HeaderProps {
  session: Session;
  navOpen: boolean;
  onToggleNav: () => void;
  /** Ends the session. Resolves false when it failed (the menu then shows an error). */
  onSignOut: () => Promise<boolean>;
}

export function Header({ session, navOpen, onToggleNav, onSignOut }: HeaderProps) {
  const [signOutFailed, setSignOutFailed] = useState(false);

  async function submitSignOut(event: React.SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    setSignOutFailed(false);
    if (!(await onSignOut())) setSignOutFailed(true);
  }

  return (
    <header className="shell-header" aria-label={t("shell.header.label")}>
      <Button
        variant="ghost"
        size="icon"
        className="shell-header__menu"
        aria-label={t("shell.nav.menu")}
        aria-expanded={navOpen}
        aria-controls="shell-nav"
        onClick={onToggleNav}
      >
        <Icon name="menu" size={20} />
      </Button>
      {/* Logo slot: empty until tenant branding exists. */}
      <span className="shell-header__logo" data-slot="tenant-logo" />
      <span className="shell-header__tenant">{session.tenant.name}</span>
      <div className="shell-header__slot" data-slot="project-switcher" />
      <div className="shell-header__slot shell-header__slot--grow" data-slot="search" />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" aria-label={t("shell.userMenu.label")} className="shell-header__user">
            <Icon name="user" size={20} />
            <span className="shell-header__user-name">{session.user.name}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>
            <span className="shell-user-menu__name">{session.user.name}</span>
            <span className="shell-user-menu__email" data-testid="user-email">
              {session.user.email}
            </span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {/* A POST form, never a link. Works without script: the action is the logout endpoint. */}
          <form method="post" action="/api/v1/auth/logout" onSubmit={(event) => void submitSignOut(event)}>
            <DropdownMenuItem asChild onSelect={(event) => event.preventDefault()}>
              <button type="submit">{t("shell.userMenu.signOut")}</button>
            </DropdownMenuItem>
          </form>
          {signOutFailed ? (
            <p role="alert" className="shell-user-menu__error">
              {t("shell.userMenu.signOutFailed")}
            </p>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
