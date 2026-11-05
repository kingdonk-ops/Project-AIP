import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

/**
 * Native `<select>` and `<textarea>` with the `Input` look (DESIGN-18): `--border-strong` for 3:1,
 * `--control-h`, the shared focus ring and the invalid border. Use them inside `FormField` (spread its
 * control props) where a Radix `Select` would change how the page behaves, e.g. react-hook-form `register`.
 */
export type NativeSelectProps = ComponentProps<"select">;

export function NativeSelect({ className, ...props }: NativeSelectProps) {
  return <select className={cn("aip-input aip-native-select", className)} {...props} />;
}

export type TextareaProps = ComponentProps<"textarea">;

export function Textarea({ className, ...props }: TextareaProps) {
  return <textarea className={cn("aip-input aip-textarea", className)} {...props} />;
}
