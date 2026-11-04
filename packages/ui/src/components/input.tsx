import type { ComponentProps } from "react";
import { cn } from "../lib/cn";
import { Icon, type IconName } from "./icon";

export interface InputProps extends ComponentProps<"input"> {
  /** A decorative 14px leading icon inside the field (DESIGN-09); the label still names the input. */
  icon?: IconName;
}

export function Input({ className, type = "text", icon, ...props }: InputProps) {
  const input = <input type={type} className={cn("aip-input", icon && "aip-input--with-icon", className)} {...props} />;
  if (!icon) return input;
  return (
    <span className="aip-input-wrap">
      <Icon name={icon} size={14} className="aip-input__icon" />
      {input}
    </span>
  );
}
