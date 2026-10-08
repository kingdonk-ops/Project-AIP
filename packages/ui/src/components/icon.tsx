import {
  TriangleAlert,
  Check,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Clock,
  Info,
  LoaderCircle,
  Minus,
  Search,
  X,
  type LucideIcon,
} from "lucide-react";
import { cn } from "../lib/cn";

const registry = {
  alert: CircleAlert,
  warning: TriangleAlert,
  check: Check,
  success: CircleCheck,
  info: Info,
  clock: Clock,
  close: X,
  "chevron-down": ChevronDown,
  search: Search,
  loader: LoaderCircle,
  minus: Minus,
} as const satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof registry;
export const iconNames = Object.keys(registry) as IconName[];

export interface IconProps {
  name: IconName;
  /** Accessible name. Without it the icon is decorative and hidden from assistive tech. */
  label?: string;
  size?: number;
  className?: string;
}

export function Icon({ name, label, size = 16, className }: IconProps) {
  const Glyph = registry[name];
  if (label) {
    return <Glyph role="img" aria-label={label} width={size} height={size} className={cn("aip-icon", className)} />;
  }
  return <Glyph aria-hidden="true" focusable="false" width={size} height={size} className={cn("aip-icon", className)} />;
}
