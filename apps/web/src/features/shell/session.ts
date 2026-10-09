import { identityLoginStart } from "@aip/api-client";
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
 * GAP (IDENTITY-02, IDENTITY-03, ACCESS-01): `GET /api/v1/me`, `POST /api/v1/auth/logout` and
 * `GET /api/v1/access/me/abilities` do not exist yet and are not in the generated client. The
 * calls below use `fetch` directly; replace them with the generated client when those routes land.
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

function isSession(value: unknown): value is Session {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  const user = v.user as Record<string, unknown> | undefined;
  const tenant = v.tenant as Record<string, unknown> | undefined;
  return (
    typeof user?.id === "string" &&
    typeof user.name === "string" &&
    typeof user.email === "string" &&
    typeof tenant?.slug === "string" &&
    typeof tenant.name === "string" &&
    Array.isArray(v.permissions)
  );
}

export const httpSessionPort: SessionPort = {
  async getSession() {
    const response = await fetch("/api/v1/me", { credentials: "same-origin", headers: { Accept: "application/json" } });
    // Fail closed: no session, a suspended tenant (403) or a route that does not exist yet (404,
    // until IDENTITY-02) all mean "not signed in". Anything else is a real failure.
    if (response.status === 401 || response.status === 403 || response.status === 404) return null;
    if (!response.ok) throw new Error(`GET /api/v1/me failed: ${response.status}`);
    const body: unknown = await response.json();
    if (!isSession(body)) throw new Error("GET /api/v1/me returned an unexpected shape");
    return body;
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
