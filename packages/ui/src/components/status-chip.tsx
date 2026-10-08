import { cn } from "../lib/cn";
import type { StatusTone } from "../tokens/tokens";
import { Icon, type IconName } from "./icon";

export interface StatusChipProps {
  tone: StatusTone;
  icon: IconName;
  /** Visible text (from `t()`); required so status is never shown by colour alone. */
  label: string;
  className?: string;
}

export function StatusChip({ tone, icon, label, className }: StatusChipProps) {
  return (
    <span className={cn("aip-status-chip", `aip-status-chip--${tone}`, className)} data-tone={tone}>
      <Icon name={icon} size={14} />
      <span>{label}</span>
    </span>
  );
}
