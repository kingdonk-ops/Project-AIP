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
    </main>
  );
}
