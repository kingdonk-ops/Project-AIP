import * as LabelPrimitive from "@radix-ui/react-label";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

export type LabelProps = ComponentProps<typeof LabelPrimitive.Root>;

export function Label({ className, ...props }: LabelProps) {
  return <LabelPrimitive.Root className={cn("aip-label", className)} {...props} />;
}
