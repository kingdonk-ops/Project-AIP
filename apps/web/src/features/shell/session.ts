import { accessGetMyAbilities, identityGetMe, identityLoginStart } from "@aip/api-client";
import { queryOptions } from "@tanstack/react-query";

/**
 * Session and identity port (DESIGN-02).
 *
 * The shell depends on `SessionPort`, never on a transport. `httpSessionPort` is the only
 * implementation production builds can reach: it talks to the API over the same-origin
 * `__Host-` session cookie (the browser holds no token). The dev stub in `./dev/` is loaded
 * through `resolveSessionPort` only in a non-production Vite build with
 * `VITE_AIP_DEV_SESSION=stub`; a production build removes it (SECURITY-08 strip manifest).
 *
 * The session is `GET /api/v1/me` (IDENTITY-02) plus the caller's tenant-wide permissions from
 * `GET /api/v1/access/me/abilities` (ACCESS-01), both through the generated client.
 * GAP (IDENTITY-03): `POST /api/v1/auth/logout` does not exist yet and is not in the generated
 * client, so logout uses `fetch` directly; switch it when the route lands.
 */

export interface Session {
  user: { id: string; name: string; email: string };
  tenant: { slug: string; name: string };
  permissions: readonly string[];
}

export type LoginStartOutcome =
  | { ok: true; method: "sso" | "password"; redirectUrl: string }
  | { ok: false; reason: "invalid_email" | "rate_limited" | "unavailable" };

export interface SessionPort {
  /** The signed-in principal, or `null` when there is no valid session. */
  getSession(): Promise<Session | null>;
  /** Starts sign-in. The caller redirects the browser to `redirectUrl`. */
  startLogin(email: string, returnTo: string): Promise<LoginStartOutcome>;
  /** Ends the session server-side. Resolves false when it could not be ended. */
  logout(): Promise<boolean>;
}

export const SESSION_QUERY_KEY = ["session"] as const;

export function sessionQuery(port: SessionPort) {
  return queryOptions({
    queryKey: SESSION_QUERY_KEY,
    queryFn: () => port.getSession(),
    staleTime: 60_000,
    retry: false,
  });
}

export const httpSessionPort: SessionPort = {
  async getSession() {
    const me = await identityGetMe({ credentials: "same-origin" });
    // Fail closed: no session (401) or a suspended tenant (403) both mean "not signed in".
    // `status` is widened: a proxy or the server can answer codes the OpenAPI document omits.
    const status: number = me.status;
    if (status === 401 || status === 403) return null;
    if (me.status !== 200) throw new Error(`GET /api/v1/me failed: ${status}`);
    const abilities = await accessGetMyAbilities(undefined, { credentials: "same-origin" });
    // Without abilities the user is signed in but holds nothing: deny by default.
    const permissions = abilities.status === 200 ? abilities.data.permissions : [];
    const { user, tenant } = me.data;
    return {
      user: { id: user.id, name: user.displayName, email: user.email },
      tenant: { slug: tenant.slug, name: tenant.name },
      permissions,
    };
  },
  async startLogin(email, returnTo) {
    try {
      const response = await identityLoginStart({ email, returnTo });
      if (response.status === 200) {
        return { ok: true, method: response.data.method, redirectUrl: response.data.redirectUrl };
      }
      if (response.status === 429) return { ok: false, reason: "rate_limited" };
      if (response.status === 422) return { ok: false, reason: "invalid_email" };
      return { ok: false, reason: "unavailable" };
    } catch {
      return { ok: false, reason: "unavailable" };
    }
  },

  async logout() {
    try {
      const response = await fetch("/api/v1/auth/logout", { method: "POST", credentials: "same-origin" });
      // 401: the session was already gone, which is the state we wanted.
      return response.status === 204 || response.status === 401;
    } catch {
      return false;
    }
  },
};

/** Picks the port. The dev stub branch is statically dead in production builds. */
export async function resolveSessionPort(): Promise<SessionPort> {
  if (!import.meta.env.PROD && import.meta.env.VITE_AIP_DEV_SESSION === "stub") {
    const stub = await import("./dev/dev-session-stub");
    return stub.devSessionPort;
  }
  return httpSessionPort;
}
