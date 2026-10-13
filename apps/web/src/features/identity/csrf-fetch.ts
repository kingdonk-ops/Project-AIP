/**
 * IDENTITY-03: the CSRF-aware fetch every generated API call uses lives in `@aip/api-client`
 * (`src/fetcher.ts`, the orval mutator): unsafe requests send `X-CSRF-Token` from the
 * `__Host-aip_csrf` cookie, and a 401 `SESSION_EXPIRED` signals the handler registered here.
 * The app passes DESIGN-02's redirect to `/login?next=<path>` (see `main.tsx`).
 */
import { onSessionExpired } from "@aip/api-client";

export { withCsrf } from "@aip/api-client";

/** Send the user to sign in again when the API says the session has ended. */
export function installSessionExpiry(redirectToLogin: () => void): () => void {
  return onSessionExpired(redirectToLogin);
}
