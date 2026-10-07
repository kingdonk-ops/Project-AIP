import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";
import { Icon } from "./icon";

export type CheckboxProps = ComponentProps<typeof CheckboxPrimitive.Root>;

export function Checkbox({ className, ...props }: CheckboxProps) {
  return (
    <CheckboxPrimitive.Root className={cn("aip-checkbox", className)} {...props}>
      <CheckboxPrimitive.Indicator className="aip-checkbox__indicator">
        {props.checked === "indeterminate" ? <Icon name="minus" size={14} /> : <Icon name="check" size={14} />}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
