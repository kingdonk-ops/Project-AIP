import { createRoute } from "@tanstack/react-router";
import "../../../features/tenancy/nav";
import { PlanAndUsagePage } from "../../../features/tenancy/PlanAndUsagePage";
import { appRoute } from "../../_app";

export const billingRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/settings/billing",
  component: PlanAndUsagePage,
});
