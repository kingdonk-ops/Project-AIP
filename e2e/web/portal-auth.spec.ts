// PORTAL-02: the portal's sign-in contract against the compose stack and real Keycloak, through the
// API only (the portal host and its sign-in pages arrive with PORTAL-03, which also owns the browser
// journey, the cross-tenant check and axe). A client's sign-in starts on the `aip-portal` client
// with aal2 asked and a redirect URI on PORTAL_ORIGIN; the portal API without a session is 401; and
// the `aip-portal` client refuses the password grant (no direct access grants).
// Runs in the skeleton lane only (`--project web --grep @skeleton`): the token probe uses the dev
// client secret, which a deployed environment never has.
import { expect, test } from "@playwright/test";

const PORTAL_ORIGIN = process.env.E2E_PORTAL_ORIGIN ?? "http://portal.localhost:8081";
const PORTAL_CLIENT_SECRET = process.env.E2E_PORTAL_CLIENT_SECRET ?? "aip_portal_dev_only_secret";
const CLIENT_EMAIL = "client.e2e@rio.example";

async function portalAuthorizeUrl(request: import("@playwright/test").APIRequestContext): Promise<URL> {
  const start = await request.post("/api/v1/auth/portal/login/start", {
    data: { email: CLIENT_EMAIL, returnTo: "/inbox" },
  });
  expect(start.status(), await start.text()).toBe(200);
  const body = (await start.json()) as { redirectUrl: string };
  return new URL(body.redirectUrl);
}

test("@skeleton a portal sign-in starts on aip-portal with aal2 and a redirect URI on the portal host", async ({ request }) => {
  const authorize = await portalAuthorizeUrl(request);
  expect(authorize.pathname).toMatch(/\/realms\/aip\/protocol\/openid-connect\/auth$/);
  expect(authorize.searchParams.get("client_id")).toBe("aip-portal");
  expect(authorize.searchParams.get("acr_values")).toBe("aal2");
  expect(authorize.searchParams.get("code_challenge_method")).toBe("S256");
  expect(authorize.searchParams.get("redirect_uri")).toBe(`${PORTAL_ORIGIN}/api/v1/auth/portal/oidc/callback`);
  expect(authorize.searchParams.has("kc_idp_hint"), "portal users are local accounts").toBe(false);
});

test("@skeleton the portal API without a session is 401 NOT_AUTHENTICATED", async ({ request }) => {
  const me = await request.get("/api/v1/portal/me");
  expect(me.status()).toBe(401);
  expect(JSON.stringify(await me.json())).toContain("NOT_AUTHENTICATED");
});

test("@skeleton the aip-portal client refuses the password grant", async ({ request }) => {
  const authorize = await portalAuthorizeUrl(request);
  const token = new URL(authorize.pathname.replace(/\/auth$/, "/token"), authorize.origin);
  const res = await request.post(token.toString(), {
    form: {
      grant_type: "password",
      client_id: "aip-portal",
      client_secret: PORTAL_CLIENT_SECRET,
      username: CLIENT_EMAIL,
      password: "not-a-real-password-1",
    },
  });
  expect(res.status()).toBe(400);
  expect(((await res.json()) as { error?: string }).error).toBe("unauthorized_client");
});
