import * as MenuPrimitive from "@radix-ui/react-dropdown-menu";
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

export const DropdownMenu = MenuPrimitive.Root;
export const DropdownMenuTrigger = MenuPrimitive.Trigger;

export function DropdownMenuContent({
  className,
  sideOffset = 4,
  ...props
}: ComponentProps<typeof MenuPrimitive.Content>) {
  return (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Content className={cn("aip-menu__content", className)} sideOffset={sideOffset} {...props} />
    </MenuPrimitive.Portal>
  );
}

export function DropdownMenuItem({ className, ...props }: ComponentProps<typeof MenuPrimitive.Item>) {
  return <MenuPrimitive.Item className={cn("aip-menu__item", className)} {...props} />;
}

export function DropdownMenuLabel({ className, ...props }: ComponentProps<typeof MenuPrimitive.Label>) {
  return <MenuPrimitive.Label className={cn("aip-menu__label", className)} {...props} />;
}

export function DropdownMenuSeparator({ className, ...props }: ComponentProps<typeof MenuPrimitive.Separator>) {
  return <MenuPrimitive.Separator className={cn("aip-menu__separator", className)} {...props} />;
}
