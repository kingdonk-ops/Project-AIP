import { usePlatformHealth } from "@aip/api-client";
import { t } from "../../terms";

/** API status from the generated client hook (STACK-03). The status value is data, not a label. */
export function ApiHealth() {
  const health = usePlatformHealth();
  let value: string;
  if (health.isPending) value = t("health.loading");
  else if (health.isError || health.data.status !== 200) value = t("health.unavailable");
  else value = health.data.data.status;
  return (
    <p>
      {t("health.label")}: <output data-testid="api-health-status">{value}</output>
    </p>
  );
}
