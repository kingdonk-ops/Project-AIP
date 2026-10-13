// Hand-written (not generated): the one fetch every generated call goes through (IDENTITY-03).
//
// - Unsafe methods (POST, PUT, PATCH, DELETE) send `X-CSRF-Token` read from the
//   `__Host-aip_csrf` cookie; the API compares it with the cookie (double submit) and checks Origin.
// - Requests are same-origin with the session cookie; the browser never holds a token.
// - A 401 whose body says `SESSION_EXPIRED` calls the handler the app registered with
//   `onSessionExpired` (the web app sends the user to `/login?next=<path>`), then the response is
//   returned as usual so callers still see the 401.
// The response shape is orval's fetch shape: `{ data, status, headers }`.

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);
export const CSRF_COOKIE = "__Host-aip_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

let sessionExpiredHandler: (() => void) | null = null;

/** Registers what happens when the API says the session has ended. Returns an unregister. */
export function onSessionExpired(handler: () => void): () => void {
  sessionExpiredHandler = handler;
  return () => {
    if (sessionExpiredHandler === handler) sessionExpiredHandler = null;
  };
}

export function readCookie(name: string, cookie: string = globalThis.document?.cookie ?? ""): string | null {
  for (const part of cookie.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

export function withCsrf(init: RequestInit = {}): RequestInit {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (UNSAFE.has(method)) {
    const token = readCookie(CSRF_COOKIE);
    if (token) headers.set(CSRF_HEADER, token);
  }
  return { credentials: "same-origin", ...init, headers };
}

function isSessionExpired(status: number, data: unknown): boolean {
  if (status !== 401 || typeof data !== "object" || data === null) return false;
  const detail = (data as { detail?: unknown }).detail;
  return typeof detail === "object" && detail !== null && (detail as { code?: unknown }).code === "SESSION_EXPIRED";
}

export const apiFetch = async <T>(url: string, init: RequestInit): Promise<T> => {
  const res = await fetch(url, withCsrf(init));
  const body = [204, 205, 304].includes(res.status) ? null : await res.text();
  let data: unknown = {};
  if (body) {
    try {
      data = JSON.parse(body);
    } catch {
      data = body;
    }
  }
  if (isSessionExpired(res.status, data)) sessionExpiredHandler?.();
  return { data, status: res.status, headers: res.headers } as T;
};
