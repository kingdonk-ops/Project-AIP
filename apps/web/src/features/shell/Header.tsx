import {
  BadgeLockup,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Icon,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { useState, type Ref } from "react";
import { JobsButton } from "../jobs/MyJobsDrawer";
import { BRAND_TOOLTIP_AT, brandText, productWord } from "./brand";
import type { Session } from "./session";
import { t } from "./t";

export interface HeaderProps {
  session: Session;
  navOpen: boolean;
  onToggleNav: () => void;
  /** Ends the session. Resolves false when it failed (the menu then shows an error). */
  onSignOut: () => Promise<boolean>;
  /** The shell returns focus here when the mobile drawer is dismissed (DESIGN-08). */
  menuButtonRef?: Ref<HTMLButtonElement> | undefined;
}

export function Header({ session, navOpen, onToggleNav, onSignOut, menuButtonRef }: HeaderProps) {
  const [signOutFailed, setSignOutFailed] = useState(false);

  async function submitSignOut(event: React.SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    setSignOutFailed(false);
    if (!(await onSignOut())) setSignOutFailed(true);
  }

  return (
    <header className="shell-header" aria-label={t("shell.header.label")}>
      <Button
        ref={menuButtonRef}
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
      <BrandLockup company={session.tenant.name} />
      <div className="shell-header__slot" data-slot="project-switcher" />
      <div className="shell-header__slot shell-header__slot--grow" data-slot="search" />
      <JobsButton />
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
          <DropdownMenuItem asChild>
            <Link to="/settings/profile/sessions">{t("identity.sessions.title")}</Link>
          </DropdownMenuItem>
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

/**
 * DESIGN-14 + DESIGN-17: "<Company> [AIP]" (lockup A) as one link to Home: the company name in the tenant's
 * brand colour, then the green AIP tag. Long names truncate and show a tooltip.
 */
function BrandLockup({ company }: { company: string }) {
  const product = productWord();
  const long = company.length > BRAND_TOOLTIP_AT;
  const link = (
    <Link to="/" className="shell-brand" aria-label={t("shell.brand.home", { company, product })}>
      {/* Logo slot: empty until tenant branding has a logo. */}
      <span className="shell-header__logo" data-slot="tenant-logo" />
      <BadgeLockup
        company={company}
        product={product}
        className="shell-brand__lockup"
        companyClassName={long ? "shell-brand__company shell-brand__company--long" : "shell-brand__company"}
      />
    </Link>
  );
  if (!long) return link;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent>{brandText(company)}</TooltipContent>
    </Tooltip>
  );
}
