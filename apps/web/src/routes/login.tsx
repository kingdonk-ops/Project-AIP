import { createRoute } from "@tanstack/react-router";
import { LoginPage, type LoginSearch } from "../features/shell/LoginPage";
import { rootRoute } from "./__root";

function validateSearch(search: Record<string, unknown>): LoginSearch {
  const result: LoginSearch = {};
  if (typeof search.next === "string") result.next = search.next;
  if (search.invited === "1" || search.invited === 1) result.invited = 1;
  if (search.signed_out === "1" || search.signed_out === 1) result.signed_out = 1;
  if (search.expired === "1" || search.expired === 1) result.expired = 1;
  if (search.error === "failed") result.error = "failed";
  return result;
}

export const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch,
  component: LoginRoute,
});

function LoginRoute() {
  return <LoginPage search={loginRoute.useSearch()} />;
}
