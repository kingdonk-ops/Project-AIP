/**
 * Domain event catalogue (ARCH-09 step 1, `GET /api/v1/admin/platform/events`): one row per event
 * version with its owning module, status, subscribers and 24-hour counts across all tenants
 * (ADR 0029: aggregate counts only, never payloads). Filters live in the URL; the API filters, and
 * the whole catalogue comes back in one page. A row (Enter, or the event link) opens its detail.
 */
import { usePlatformListEvents, type EventSummary, type PlatformListEventsParams } from "@aip/api-client";
import {
  RegisterTable,
  type RegisterColumn,
  type RegisterFilter,
  type RegisterQuery,
  type RegisterQueryResult,
  type Translate,
} from "@aip/ui";
import { Link, useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { t } from "../shell/t";
import { EventStatusChip } from "./EventStatusChip";
import { EVENT_STATUSES } from "./search";

/** Filter options whose "label" is an identifier (a module id or a version number), shown as is. */
const CODE = "code:";
const translate: Translate = (key, params) => (key.startsWith(CODE) ? key.slice(CODE.length) : t(key, params));

function paramsOf(query: RegisterQuery): PlatformListEventsParams {
  const params: PlatformListEventsParams = {};
  const { module, status, version } = query.filters;
  if (typeof module === "string") params.module = module;
  if (status === "active" || status === "deprecated") params.status = status;
  if (typeof version === "string" && /^\d{1,4}$/.test(version)) params.version = Number(version);
  return params;
}

function useCatalogue(query: RegisterQuery): RegisterQueryResult<EventSummary> {
  const result = usePlatformListEvents(paramsOf(query));
  const response = result.data;
  return {
    data: response?.status === 200 ? { items: response.data.events, nextCursor: null } : undefined,
    isPending: result.isPending,
    isError: result.isError || (response !== undefined && response.status !== 200),
    refetch: () => void result.refetch(),
  };
}

function rowKey(event: EventSummary): string {
  return `${event.name}@${event.version}`;
}

const columns: readonly RegisterColumn<EventSummary>[] = [
  {
    id: "event",
    headerKey: "arch.events.col.event",
    mono: true,
    cell: (event) => (
      <Link
        to="/admin/platform/events/$eventName"
        params={{ eventName: event.name }}
        aria-label={t("arch.events.open", { name: event.name, version: event.version })}
      >
        {event.name}
      </Link>
    ),
    csv: (event) => event.name,
  },
  { id: "version", headerKey: "arch.events.col.version", cell: (event) => event.version },
  { id: "module", headerKey: "arch.events.col.module", mono: true, cell: (event) => event.module },
  { id: "status", headerKey: "arch.events.col.status", cell: (event) => <EventStatusChip status={event.status} /> },
  {
    id: "subscribers",
    headerKey: "arch.events.col.subscribers",
    cell: (event) => (event.subscribers.length ? event.subscribers.join(", ") : t("arch.events.subscribers.none")),
  },
  { id: "published24h", headerKey: "arch.events.col.published_24h", cell: (event) => event.published24h },
  { id: "failed24h", headerKey: "arch.events.col.failed_24h", cell: (event) => event.failed24h },
];

export interface CataloguePageProps {
  query: RegisterQuery;
  onQueryChange: (next: RegisterQuery) => void;
  permissions: readonly string[];
}

export function CataloguePage({ query, onQueryChange, permissions }: CataloguePageProps) {
  const navigate = useNavigate();
  // The unfiltered catalogue gives the module and version choices (the same request when no filter is set).
  const all = usePlatformListEvents({});
  const filters = useMemo<RegisterFilter[]>(() => {
    const events = all.data?.status === 200 ? all.data.data.events : [];
    const modules = [...new Set(events.map((e) => e.module))].sort();
    const versions = [...new Set(events.map((e) => e.version))].sort((a, b) => a - b);
    return [
      {
        id: "module",
        kind: "select",
        labelKey: "arch.events.filter.module",
        quick: true,
        options: modules.map((m) => ({ value: m, labelKey: `${CODE}${m}` })),
      },
      {
        id: "status",
        kind: "select",
        labelKey: "arch.events.filter.status",
        quick: true,
        options: EVENT_STATUSES.map((s) => ({ value: s, labelKey: `arch.events.status.${s}` })),
      },
      {
        id: "version",
        kind: "select",
        labelKey: "arch.events.filter.version",
        options: versions.map((v) => ({ value: String(v), labelKey: `${CODE}${v}` })),
      },
    ];
  }, [all.data]);

  return (
    <section className="aip-page" aria-labelledby="platform-events-title">
      <h1 id="platform-events-title">{t("arch.events.catalogue.title")}</h1>
      <p>{t("arch.events.catalogue.intro")}</p>
      <RegisterTable
        id="platform-events"
        captionKey="arch.events.catalogue.caption"
        columns={columns}
        filters={filters}
        query={query}
        onQueryChange={onQueryChange}
        useQuery={useCatalogue}
        rowId={rowKey}
        onOpenRow={(event) => void navigate({ to: "/admin/platform/events/$eventName", params: { eventName: event.name } })}
        permissions={permissions}
        search={false}
        translate={translate}
      />
    </section>
  );
}
