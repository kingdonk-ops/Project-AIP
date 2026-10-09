import { Icon, Tooltip, TooltipContent, TooltipTrigger } from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { useRef, type KeyboardEvent } from "react";
import { registeredNavItems, visibleNavGroups, type NavItem } from "./nav-registry";
import { t } from "./t";

export interface NavRailProps {
  permissions: readonly string[];
  /** Defaults to the module registry; tests pass their own list. */
  items?: readonly NavItem[] | undefined;
  /** Mobile: whether the collapsed rail is showing. */
  open: boolean;
  onNavigate?: () => void;
}

export function NavRail({ permissions, items = registeredNavItems(), open, onNavigate }: NavRailProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const groups = visibleNavGroups(items, permissions);

  // Arrow keys, Home and End move focus between rail links; Tab still leaves the rail.
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(event.key)) return;
    const links = Array.from(listRef.current?.querySelectorAll<HTMLAnchorElement>("a") ?? []);
    if (links.length === 0) return;
    const current = links.indexOf(document.activeElement as HTMLAnchorElement);
    let next = current;
    if (event.key === "ArrowDown") next = (current + 1) % links.length;
    if (event.key === "ArrowUp") next = (current - 1 + links.length) % links.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = links.length - 1;
    event.preventDefault();
    links[next]?.focus();
  }

  return (
    <nav id="shell-nav" className="shell-rail" aria-label={t("shell.nav.label")} data-open={open ? "true" : "false"}>
      {/* The arrow-key handler is a progressive enhancement over native Tab order. */}
      <div ref={listRef} className="shell-rail__list" onKeyDown={onKeyDown}>
        {groups.map((group) => (
          <ul key={group.section} className="shell-rail__group" aria-label={t(`shell.nav.section.${group.section}`)}>
            {group.items.map((item) => (
              <li key={item.id}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Link
                      to={item.to}
                      className="shell-rail__link"
                      activeProps={{ "aria-current": "page", "data-active": "true" }}
                      activeOptions={{ exact: item.to === "/" }}
                      onClick={onNavigate}
                    >
                      <Icon name={item.icon} size={20} />
                      <span className="shell-rail__label">{t(item.termKey)}</span>
                    </Link>
                  </TooltipTrigger>
                  <TooltipContent side="right">{t(item.termKey)}</TooltipContent>
                </Tooltip>
              </li>
            ))}
          </ul>
        ))}
      </div>
    </nav>
  );
}
