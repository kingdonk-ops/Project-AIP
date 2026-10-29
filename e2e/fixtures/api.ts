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

/** The `sid` of the browser's aip realm SSO session, from Keycloak's identity cookie (a JWT). */
async function keycloakSid(context: BrowserContext, realmUrl: string): Promise<string> {
  const identity = (await context.cookies(realmUrl)).find((c) => c.name === "KEYCLOAK_IDENTITY");
  if (!identity) throw new Error("no KEYCLOAK_IDENTITY cookie for the aip realm");
  const claims = JSON.parse(Buffer.from(identity.value.split(".")[1] ?? "", "base64url").toString()) as Record<string, unknown>;
  const sid = claims.sid ?? claims.session_state;
  if (typeof sid !== "string") throw new Error("the identity cookie has no sid");
  return sid;
}

/**
 * Whether the browser's Keycloak SSO session in the aip realm still exists, asked of Keycloak's
 * admin API with the `aip-admin` service account (the client the API's revoke job uses). Compose
 * only: CI passes its dev secret as `E2E_KC_ADMIN_CLIENT_SECRET`. A `prompt=none` probe cannot
 * answer this, because aip-api demands aal2 and a password-only session never satisfies it.
 */
export async function keycloakSso(context: BrowserContext, authorize: string, email: string): Promise<"active" | "ended"> {
  const secret = process.env.E2E_KC_ADMIN_CLIENT_SECRET?.trim();
  if (!secret) throw new Error("Missing E2E_KC_ADMIN_CLIENT_SECRET");
  const realmUrl = authorize.replace(/\/protocol\/openid-connect\/auth.*$/, "");
  const sid = await keycloakSid(context, `${realmUrl}/`);
  const token = await fetch(`${realmUrl}/protocol/openid-connect/token`, {
    method: "POST",
    body: new URLSearchParams({ grant_type: "client_credentials", client_id: "aip-admin", client_secret: secret }),
  });
  if (!token.ok) throw new Error(`aip-admin token: ${token.status}`);
  const auth = { authorization: `Bearer ${((await token.json()) as { access_token: string }).access_token}` };
  const admin = realmUrl.replace("/realms/", "/admin/realms/");
  const users = (await (await fetch(`${admin}/users?exact=true&email=${encodeURIComponent(email)}`, { headers: auth })).json()) as {
    id: string;
  }[];
  if (users.length !== 1) throw new Error(`expected one aip realm user ${email}, got ${users.length}`);
  const sessions = (await (await fetch(`${admin}/users/${users[0]?.id}/sessions`, { headers: auth })).json()) as { id: string }[];
  return sessions.some((s) => s.id === sid) ? "active" : "ended";
}
