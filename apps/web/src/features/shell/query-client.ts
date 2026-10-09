import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

/** True for a generated-client response (`{status: 401}`) or an error carrying `status: 401`. */
export function isUnauthorized(value: unknown): boolean {
  return typeof value === "object" && value !== null && (value as { status?: unknown }).status === 401;
}

/**
 * Query client whose caches report an expired session: a 401 from any later API call calls
 * `onSessionExpired` (the app clears the cache and redirects to /login).
 */
export function createQueryClient(onSessionExpired: () => void): QueryClient {
  const check = (value: unknown) => {
    if (isUnauthorized(value)) onSessionExpired();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onSuccess: check, onError: check }),
    mutationCache: new MutationCache({ onSuccess: check, onError: check }),
  });
}
