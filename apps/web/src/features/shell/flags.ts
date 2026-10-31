/**
 * The tenant's release flags (ARCH-08) as the shell reads them (DESIGN-15). `GET /settings/flags` is
 * fetched once per session: a successful read never goes stale, signing out clears the cache, and the flags
 * page writes each change back into the same query, so the rail updates at once.
 */
import {
  getPlatformListFlagsQueryKey,
  usePlatformListFlags,
  type FeatureFlag,
  type platformListFlagsResponse,
} from "@aip/api-client";
import type { QueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

/** Permission that unlocks the flags page; the API enforces it on `PUT /settings/flags/{flag}`. */
export const FLAGS_MANAGE = "tenant.flags.manage";

/** Every known flag with its value, or `undefined` while loading or after a failed read. */
export function useFeatureFlags(): { flags: readonly FeatureFlag[] | undefined; isPending: boolean; refetch: () => void } {
  // Only a successful read is kept for the session; a 401 or 5xx answer is fetched again next time.
  const query = usePlatformListFlags({
    query: { staleTime: (current) => (current.state.data?.status === 200 ? Infinity : 0) },
  });
  return {
    flags: query.data?.status === 200 ? query.data.data.flags : undefined,
    isPending: query.isPending,
    refetch: () => void query.refetch(),
  };
}

/** Names of the flags that are on. Empty until they load, so flagged nav items stay hidden. */
export function useEnabledFlags(): readonly string[] {
  const { flags } = useFeatureFlags();
  return useMemo(() => (flags ?? []).filter((flag) => flag.enabled).map((flag) => flag.flag), [flags]);
}

/** Writes one changed flag into the cached list, so the rail and the flags page follow without a refetch. */
export function storeFlag(queryClient: QueryClient, changed: FeatureFlag): void {
  queryClient.setQueryData<platformListFlagsResponse>(getPlatformListFlagsQueryKey(), (current) => {
    if (current?.status !== 200) return current;
    const flags = current.data.flags.map((flag) => (flag.flag === changed.flag ? changed : flag));
    return { ...current, data: { ...current.data, flags } };
  });
}
