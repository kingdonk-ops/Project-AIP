/**
 * IDENTITY-04 step 8: a critical action answered 401 `STEP_UP_REQUIRED` sends the browser to
 * Keycloak for a fresh second factor, then back to the same page, which offers to retry.
 *
 * - `startStepUp(response, pending)`: when `response` is that 401, keep the pending form state in
 *   `sessionStorage` and `window.location.assign` the step-up URL (returning to this page). The
 *   URL must be the API's own step-up start path; anything else is ignored.
 * - `takePendingStepUp(key)`: on return, the saved state for `key` (once; it expires after
 *   15 minutes), so the page can offer the retry (terms `identity.stepUp.*`).
 *
 * Keycloak's pages do all credential entry: this app has no password, TOTP or WebAuthn UI.
 */

export const STEP_UP_START_PATH = "/api/v1/auth/step-up/start";
export const PENDING_KEY = "aip:step-up:pending";
const PENDING_TTL_MS = 15 * 60 * 1000;

interface ApiResponse {
  status: number;
  data: unknown;
}

interface Pending<T> {
  key: string;
  path: string;
  savedAt: number;
  state: T;
}

export interface StepUpDeps {
  storage: Pick<Storage, "getItem" | "setItem" | "removeItem">;
  assign: (url: string) => void;
  location: Pick<Location, "pathname" | "search">;
  now: () => number;
}

function defaultDeps(): StepUpDeps {
  return {
    storage: window.sessionStorage,
    assign: (url) => window.location.assign(url),
    location: window.location,
    now: () => Date.now(),
  };
}

/** The API's step-up URL when `response` is 401 `STEP_UP_REQUIRED`, else `null`. */
export function stepUpUrlOf(response: ApiResponse): string | null {
  if (response.status !== 401 || typeof response.data !== "object" || response.data === null) return null;
  const detail = (response.data as { detail?: unknown }).detail;
  if (typeof detail !== "object" || detail === null) return null;
  const { code, stepUpUrl } = detail as { code?: unknown; stepUpUrl?: unknown };
  if (code !== "STEP_UP_REQUIRED" || typeof stepUpUrl !== "string") return null;
  return stepUpUrl.startsWith(`${STEP_UP_START_PATH}?`) || stepUpUrl === STEP_UP_START_PATH ? stepUpUrl : null;
}

/** Start the step-up for `response`; true when the browser is being sent to Keycloak. */
export function startStepUp<T>(
  response: ApiResponse,
  pending: { key: string; state: T },
  deps: StepUpDeps = defaultDeps(),
): boolean {
  if (stepUpUrlOf(response) === null) return false;
  const path = `${deps.location.pathname}${deps.location.search}`;
  const saved: Pending<T> = { key: pending.key, path, savedAt: deps.now(), state: pending.state };
  try {
    deps.storage.setItem(PENDING_KEY, JSON.stringify(saved));
  } catch {
    // Storage full or blocked: the step-up still works, only the retry offer is lost.
  }
  deps.assign(`${STEP_UP_START_PATH}?returnTo=${encodeURIComponent(path)}`);
  return true;
}

/** The state saved before the step-up for `key` on this page, once; `null` when there is none. */
export function takePendingStepUp<T>(key: string, deps: StepUpDeps = defaultDeps()): T | null {
  let raw: string | null;
  try {
    raw = deps.storage.getItem(PENDING_KEY);
  } catch {
    return null;
  }
  if (raw === null) return null;
  let saved: Pending<T>;
  try {
    saved = JSON.parse(raw) as Pending<T>;
  } catch {
    deps.storage.removeItem(PENDING_KEY);
    return null;
  }
  if (saved.key !== key) return null;
  deps.storage.removeItem(PENDING_KEY);
  const here = `${deps.location.pathname}${deps.location.search}`;
  if (saved.path !== here || deps.now() - saved.savedAt > PENDING_TTL_MS) return null;
  return saved.state;
}
