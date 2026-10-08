import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

export const buttonVariants = cva("aip-button", {
  variants: {
    variant: {
      primary: "aip-button--primary",
      secondary: "aip-button--secondary",
      ghost: "aip-button--ghost",
      danger: "aip-button--danger",
    },
    size: {
      default: "aip-button--default",
      icon: "aip-button--icon",
    },
  },
  defaultVariants: { variant: "primary", size: "default" },
});

export interface ButtonProps extends ComponentProps<"button">, VariantProps<typeof buttonVariants> {
  /** Render the child element (e.g. a router link) with button styling. */
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, type, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      className={cn(buttonVariants({ variant, size }), className)}
      {...(asChild ? {} : { type: type ?? "button" })}
      {...props}
    />
  );
}
