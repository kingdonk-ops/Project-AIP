// TESTING-12: API calls made from inside the page, so the browser sends the session cookie, Origin
// and the CSRF header exactly like the app does; and a probe for the Keycloak SSO session.
import type { BrowserContext, Page, Request } from "@playwright/test";
import { CSRF_COOKIE } from "./login";

export interface ApiResult {
  status: number;
  json: Record<string, unknown> | null;
}

export async function apiCall(page: Page, method: string, path: string, body?: unknown): Promise<ApiResult> {
  return page.evaluate(
    async ({ method, path, body, csrfCookie }) => {
      const token = document.cookie
        .split("; ")
        .find((c) => c.startsWith(`${csrfCookie}=`))
        ?.slice(csrfCookie.length + 1);
      const response = await fetch(path, {
        method,
        credentials: "same-origin",
        headers: { "content-type": "application/json", "x-csrf-token": token ?? "" },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      const text = await response.text();
      return { status: response.status, json: text ? (JSON.parse(text) as Record<string, unknown>) : null };
    },
    { method, path, body, csrfCookie: CSRF_COOKIE },
  );
}

/** The aip realm's authorize request that the app's /login sends the browser to. */
export function isAuthorizeRequest(request: Request): boolean {
  return /\/realms\/aip\/protocol\/openid-connect\/auth\b/.test(request.url());
}

/**
 * Whether the browser still has a Keycloak SSO session in the aip realm: replay the app's authorize
 * request with `prompt=none` and no IdP hint. Keycloak answers the redirect URI with a code while
 * the session lives and with `error=login_required` once it is gone. The callback is answered here,
 * never by the API, so the probe creates no app session.
 */
export async function keycloakSso(context: BrowserContext, authorize: string): Promise<string> {
  const url = new URL(authorize);
  url.searchParams.set("prompt", "none");
  url.searchParams.delete("kc_idp_hint");
  url.searchParams.delete("login_hint");
  const page = await context.newPage();
  try {
    let landed: URL | null = null;
    await page.route(
      (u) => u.pathname === "/api/v1/auth/oidc/callback",
      (route) => {
        landed = new URL(route.request().url());
        return route.fulfill({ status: 200, contentType: "text/plain", body: "probe" });
      },
    );
    await page.goto(url.toString());
    const params = (landed as URL | null)?.searchParams;
    if (params?.get("code")) return "active";
    if (params?.get("error") === "login_required") return "ended";
    return `unexpected: ${page.url()}`;
  } finally {
    await page.close();
  }
}
