import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

export const badgeVariants = cva("aip-badge", {
  variants: {
    tone: {
      accent: "aip-badge--accent",
      neutral: "aip-badge--neutral",
      outline: "aip-badge--outline",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export interface BadgeProps extends ComponentProps<"span">, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
