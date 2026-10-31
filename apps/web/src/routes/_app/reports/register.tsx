import { createRoute } from "@tanstack/react-router";
import "../../../features/reports/nav";
import "../../../features/reports/reports.css";
import { ReportsRegister } from "../../../features/reports/ReportsRegister";
import { reportsQuery, toSearch, validateReportsSearch } from "../../../features/reports/search";
import { appRoute } from "../../_app";

export const reportsRegisterRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/reports/register",
  validateSearch: validateReportsSearch,
  component: ReportsRegisterPage,
});

function ReportsRegisterPage() {
  const search = reportsRegisterRoute.useSearch();
  const navigate = reportsRegisterRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <ReportsRegister
      query={reportsQuery(search)}
      permissions={session.permissions}
      onQueryChange={(next) => void navigate({ search: toSearch(next), replace: true })}
    />
  );
}
