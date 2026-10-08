import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

/** Dense register table: row height follows `--row-h` (compact 32px, comfortable 40px). */
export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="aip-table__wrap">
      <table className={cn("aip-table", className)} {...props} />
    </div>
  );
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("aip-table__caption", className)} {...props} />;
}

export function TableHeader({ className, ...props }: ComponentProps<"thead">) {
  return <thead className={cn("aip-table__header", className)} {...props} />;
}

export function TableBody({ className, ...props }: ComponentProps<"tbody">) {
  return <tbody className={cn("aip-table__body", className)} {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr className={cn("aip-table__row", className)} {...props} />;
}

export function TableHead({ className, scope = "col", ...props }: ComponentProps<"th">) {
  return <th scope={scope} className={cn("aip-table__head", className)} {...props} />;
}

export function TableCell({ className, ...props }: ComponentProps<"td">) {
  return <td className={cn("aip-table__cell", className)} {...props} />;
}
