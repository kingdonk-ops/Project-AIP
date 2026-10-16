import type { EventSummaryStatus } from "@aip/api-client";
import { StatusChip } from "@aip/ui";
import { t } from "../shell/t";

/** An event version's status as a chip with text and icon, never colour alone. */
export function EventStatusChip({ status }: { status: EventSummaryStatus }) {
  return status === "deprecated" ? (
    <StatusChip tone="warning" icon="warning" label={t("arch.events.status.deprecated")} />
  ) : (
    <StatusChip tone="success" icon="success" label={t("arch.events.status.active")} />
  );
}
