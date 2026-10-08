import * as SelectPrimitive from "@radix-ui/react-select";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";
import { Icon } from "./icon";

export const Select = SelectPrimitive.Root;

export function SelectValue(props: ComponentProps<typeof SelectPrimitive.Value>) {
  return <SelectPrimitive.Value {...props} />;
}

export function SelectTrigger({ className, children, ...props }: ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger className={cn("aip-select__trigger", className)} {...props}>
      {children}
      <SelectPrimitive.Icon asChild>
        <Icon name="chevron-down" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

export function SelectContent({
  className,
  children,
  position = "popper",
  ...props
}: ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content className={cn("aip-select__content", className)} position={position} {...props}>
        <SelectPrimitive.Viewport className="aip-select__viewport">{children}</SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

export function SelectItem({ className, children, ...props }: ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item className={cn("aip-select__item", className)} {...props}>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="aip-select__indicator">
        <Icon name="check" />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
}
