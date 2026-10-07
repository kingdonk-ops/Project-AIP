import { cn } from "../lib/cn";
import { Icon } from "./icon";

export interface SpinnerProps {
  /** Announced loading text (from `t()`), visually hidden. */
  label: string;
  size?: number;
  className?: string;
}

export function Spinner({ label, size = 16, className }: SpinnerProps) {
  return (
    <span role="status" className={cn("aip-spinner", className)}>
      <Icon name="loader" size={size} className="aip-spinner__icon" />
      <span className="aip-visually-hidden">{label}</span>
    </span>
  );
}
