import { usePlatformHealth } from "@aip/api-client";
import { createRoute } from "@tanstack/react-router";
import { t } from "../terms";
import { rootRoute } from "./__root";

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomePage,
});

function HomePage() {
  return (
    <main>
      <h1>{t("app.title")}</h1>
      <ApiHealth />
    </main>
  );
}

/** API status from the generated client hook (STACK-03). The status value is data, not a label. */
function ApiHealth() {
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
