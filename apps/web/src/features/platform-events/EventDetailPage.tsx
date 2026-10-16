/**
 * Event detail (ARCH-09 step 2, `GET /api/v1/admin/platform/events/{eventName}`): one section per
 * version with its status, subscribers and read-only JSON Schema. "Deprecate" confirms in a dialog,
 * calls `POST .../versions/{version}/deprecate` and toasts; it is hidden once a version is
 * deprecated (a deprecated version still validates and is delivered).
 */
import {
  getPlatformGetEventQueryKey,
  getPlatformListEventsQueryKey,
  usePlatformDeprecateEventVersion,
  usePlatformGetEvent,
  type EventVersionDetail,
} from "@aip/api-client";
import { Button, confirm, ErrorState, LoadingState, toast } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { t } from "../shell/t";
import { EventStatusChip } from "./EventStatusChip";

function VersionSection({
  detail,
  onDeprecate,
  busy,
}: {
  detail: EventVersionDetail;
  onDeprecate: () => void;
  busy: boolean;
}) {
  const headingId = `event-version-${detail.version}`;
  const schemaId = `${headingId}-schema`;
  return (
    <section className="platform-events__version" aria-labelledby={headingId}>
      <div className="platform-events__version-header">
        <h2 id={headingId}>{t("arch.events.detail.version", { version: detail.version })}</h2>
        <EventStatusChip status={detail.status} />
        {detail.status === "active" ? (
          <Button variant="secondary" onClick={onDeprecate} disabled={busy}>
            {t("arch.events.detail.deprecate")}
          </Button>
        ) : null}
      </div>
      <h3>{t("arch.events.detail.subscribers")}</h3>
      {detail.subscribers.length ? (
        <ul>
          {detail.subscribers.map((subscriber) => (
            <li key={subscriber} className="platform-events__mono">
              {subscriber}
            </li>
          ))}
        </ul>
      ) : (
        <p>{t("arch.events.subscribers.none")}</p>
      )}
      <h3 id={schemaId}>{t("arch.events.detail.schema")}</h3>
      <pre className="platform-events__schema" aria-labelledby={schemaId}>
        <code>{JSON.stringify(detail.schema, null, 2)}</code>
      </pre>
    </section>
  );
}

export function EventDetailPage({ eventName }: { eventName: string }) {
  const query = usePlatformGetEvent(eventName);
  const queryClient = useQueryClient();
  const deprecate = usePlatformDeprecateEventVersion();
  const response = query.data;

  const onDeprecate = async (version: number) => {
    const params = { name: eventName, version };
    const ok = await confirm({
      titleKey: "arch.events.detail.deprecate_title",
      bodyKey: "arch.events.detail.deprecate_body",
      confirmKey: "arch.events.detail.deprecate_confirm",
      params,
      tone: "danger",
    });
    if (!ok) return;
    const result = await deprecate.mutateAsync({ eventName, version }).catch(() => undefined);
    if (result?.status === 200) toast.success("arch.events.detail.deprecated_toast", params);
    else toast.error("arch.events.dead_letter.action_failed");
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: getPlatformGetEventQueryKey(eventName) }),
      queryClient.invalidateQueries({ queryKey: getPlatformListEventsQueryKey().slice(0, 1) }),
    ]);
  };

  return (
    <section className="aip-page platform-events" aria-labelledby="platform-event-title">
      <p>
        <Link to="/admin/platform/events">{t("arch.events.detail.back")}</Link>
      </p>
      <h1 id="platform-event-title" className="platform-events__mono">
        {eventName}
      </h1>
      <p>{t("arch.events.detail.intro")}</p>
      {query.isPending ? (
        <LoadingState variant="spinner" translate={t} />
      ) : response?.status !== 200 ? (
        <ErrorState
          error={response ? { status: response.status, requestId: response.headers.get("x-request-id") } : {}}
          onRetry={() => void query.refetch()}
          translate={t}
        />
      ) : (
        response.data.versions.map((detail) => (
          <VersionSection
            key={detail.version}
            detail={detail}
            busy={deprecate.isPending}
            onDeprecate={() => void onDeprecate(detail.version)}
          />
        ))
      )}
    </section>
  );
}
