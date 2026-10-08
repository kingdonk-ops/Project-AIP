import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

export type InputProps = ComponentProps<"input">;

export function Input({ className, type = "text", ...props }: InputProps) {
  return <input type={type} className={cn("aip-input", className)} {...props} />;
}
