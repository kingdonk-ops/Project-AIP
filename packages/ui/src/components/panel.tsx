import { useId, type ComponentProps, type ReactNode } from "react";
import { cn } from "../lib/cn";

export interface PanelProps extends Omit<ComponentProps<"section">, "title"> {
  /** Visible heading; it also names the section, so a panel with a heading is a labelled region. */
  heading?: ReactNode;
  /** Heading level for the document outline (default 2). */
  headingLevel?: 2 | 3 | 4;
  /** Buttons or links shown at the right of the heading row. */
  actions?: ReactNode;
}

/**
 * A white, hairline-bordered surface on the off-white canvas (DESIGN-09). The border is decorative
 * (`--border-subtle`); controls inside keep their own `--border-strong` borders. No shadow.
 */
export function Panel({ heading, headingLevel = 2, actions, className, children, ...props }: PanelProps) {
  const headingId = useId();
  const Heading = `h${headingLevel}` as const;
  const labelled = heading !== undefined && heading !== null;
  return (
    <section
      className={cn("aip-panel", className)}
      aria-labelledby={labelled && !props["aria-label"] ? headingId : undefined}
      {...props}
    >
      {(labelled || actions) && (
        <div className="aip-panel__header">
          {labelled && (
            <Heading id={headingId} className="aip-panel__heading">
              {heading}
            </Heading>
          )}
          {actions && <div className="aip-panel__actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
