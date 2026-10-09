/**
 * AIP_DEV_SESSION_STUB: development-only session port backed by the shared fixture tenants
 * (AGENTS.md: kaefer-demo / alice@kaefer.test, tenant-b / bob@acme.test). It exists only until
 * IDENTITY-02/03 issue real sessions, and it is replaceable through the `SessionPort` interface.
 *
 * It is NEVER part of a production build: `resolveSessionPort` imports it only behind
 * `!import.meta.env.PROD`, the strip manifest (config/prod-strip-manifest.txt) fails the build
 * check if this marker or file name appears in `apps/web/dist`, and the module refuses to run when
 * `import.meta.env.PROD` is true. The "session" is a fixture id in localStorage, not a credential.
 */
import type { LoginStartOutcome, Session, SessionPort } from "../session";

if (import.meta.env.PROD) {
  throw new Error("AIP_DEV_SESSION_STUB must not be loaded in a production build");
}

const STORAGE_KEY = "aip.dev-session-stub";

const fixtureSessions: Record<string, Session> = {
  "alice@kaefer.test": {
    user: { id: "00000000-0000-4000-8000-0000000000a1", name: "Alice Anderson", email: "alice@kaefer.test" },
    tenant: { slug: "kaefer-demo", name: "Kaefer Demo" },
    permissions: ["project.view", "audit.view"],
  },
  "bob@acme.test": {
    user: { id: "00000000-0000-4000-8000-0000000000b1", name: "Bob Brown", email: "bob@acme.test" },
    tenant: { slug: "tenant-b", name: "Tenant B" },
    permissions: ["project.view"],
  },
};

export const devSessionPort: SessionPort = {
  getSession() {
    try {
      const email = window.localStorage.getItem(STORAGE_KEY);
      return Promise.resolve((email && fixtureSessions[email]) || null);
    } catch {
      return Promise.resolve(null);
    }
  },

  startLogin(email, returnTo): Promise<LoginStartOutcome> {
    const key = email.trim().toLowerCase();
    if (!key.includes("@")) return Promise.resolve({ ok: false, reason: "invalid_email" });
    // Enumeration-safe like the real API: an unknown email also "redirects", back to the login page.
    if (!(key in fixtureSessions)) {
      return Promise.resolve({ ok: true, method: "sso", redirectUrl: "/login?error=failed" });
    }
    window.localStorage.setItem(STORAGE_KEY, key);
    return Promise.resolve({ ok: true, method: "sso", redirectUrl: returnTo });
  },

  logout() {
    window.localStorage.removeItem(STORAGE_KEY);
    return Promise.resolve(true);
  },
};
