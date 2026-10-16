/**
 * Dead-letter queue (ARCH-09 step 3, `GET /api/v1/admin/platform/events/dead-letter`): events that
 * used up their attempts, across tenants, keyset-paged (`limit`/`after`, the API's `nextAfter` is
 * the register's cursor). Metadata only: the API never returns payloads and `lastError` is a
 * summary (ADR 0030). Row actions retry (`POST .../{id}/retry`) or discard with a reason
 * (`POST .../{id}/discard`); "Retry selected" retries each row and reports how many went through.
 * A 404 means another operator already acted: the page says so and refetches.
 */
import {
  getPlatformListDeadLettersQueryKey,
  usePlatformDiscardDeadLetter,
  usePlatformListDeadLetters,
  usePlatformRetryDeadLetter,
  type DeadLetter,
} from "@aip/api-client";
import {
  Button,
  RegisterTable,
  toast,
  type BulkAction,
  type RegisterColumn,
  type RegisterQuery,
  type RegisterQueryResult,
} from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { t } from "../shell/t";
import { EVENTS_MANAGE } from "./access";
import { DiscardDialog } from "./DiscardDialog";

type Outcome = "done" | "gone" | "failed";

function outcomeOf(status: number | undefined): Outcome {
  if (status === 200) return "done";
  if (status === 404) return "gone";
  return "failed";
}

function useDeadLetters(query: RegisterQuery): RegisterQueryResult<DeadLetter> {
  const result = usePlatformListDeadLetters({ limit: query.limit, ...(query.cursor ? { after: query.cursor } : {}) });
  const response = result.data;
  return {
    data: response?.status === 200 ? { items: response.data.items, nextCursor: response.data.nextAfter } : undefined,
    isPending: result.isPending,
    isError: result.isError || (response !== undefined && response.status !== 200),
    refetch: () => void result.refetch(),
  };
}

const when = new Intl.DateTimeFormat("en-AU", { dateStyle: "medium", timeStyle: "short" });

function EventId({ id }: { id: string }) {
  return (
    <span className="platform-events__id">
      <code>{id}</code>
      <Button
        variant="ghost"
        aria-label={t("arch.events.dead_letter.copy_id", { id })}
        onClick={() => {
          void navigator.clipboard?.writeText(id).then(() => toast.info("arch.events.dead_letter.copied"));
        }}
      >
        {t("arch.events.dead_letter.copy")}
      </Button>
    </span>
  );
}

export interface DeadLetterPageProps {
  query: RegisterQuery;
  onQueryChange: (next: RegisterQuery) => void;
  permissions: readonly string[];
}

export function DeadLetterPage({ query, onQueryChange, permissions }: DeadLetterPageProps) {
  const queryClient = useQueryClient();
  const retry = usePlatformRetryDeadLetter();
  const discard = usePlatformDiscardDeadLetter();
  const [discarding, setDiscarding] = useState<DeadLetter | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: getPlatformListDeadLettersQueryKey().slice(0, 1) });

  const retryOne = async (id: string): Promise<Outcome> =>
    outcomeOf((await retry.mutateAsync({ eventId: id }).catch(() => undefined))?.status);

  const report = (outcome: Outcome, doneKey: string) => {
    if (outcome === "done") toast.success(doneKey);
    else if (outcome === "gone") toast.info("arch.events.dead_letter.already_handled");
    else toast.error("arch.events.dead_letter.action_failed");
  };

  const onRetry = async (row: DeadLetter) => {
    report(await retryOne(row.id), "arch.events.dead_letter.retried_toast");
    await refresh();
  };

  const onRetryMany = async (rows: readonly DeadLetter[]) => {
    let done = 0;
    for (const row of rows) if ((await retryOne(row.id)) === "done") done += 1;
    toast.info("arch.events.dead_letter.retried_some", { done, total: rows.length });
    await refresh();
  };

  const onDiscard = async (reason: string) => {
    if (!discarding) return;
    const response = await discard.mutateAsync({ eventId: discarding.id, data: { reason } }).catch(() => undefined);
    const outcome = outcomeOf(response?.status);
    if (outcome !== "failed") setDiscarding(null);
    report(outcome, "arch.events.dead_letter.discarded_toast");
    await refresh();
  };

  const columns: RegisterColumn<DeadLetter>[] = [
      { id: "id", headerKey: "arch.events.dead_letter.col.id", cell: (row) => <EventId id={row.id} /> },
      { id: "event", headerKey: "arch.events.dead_letter.col.event", mono: true, cell: (row) => row.eventName },
      { id: "version", headerKey: "arch.events.dead_letter.col.version", cell: (row) => row.eventVersion },
      { id: "tenant", headerKey: "arch.events.dead_letter.col.tenant", mono: true, cell: (row) => row.tenantId },
      { id: "attempts", headerKey: "arch.events.dead_letter.col.attempts", cell: (row) => row.attempts },
      {
        id: "lastError",
        headerKey: "arch.events.dead_letter.col.last_error",
        cell: (row) => row.lastError ?? t("arch.events.dead_letter.no_error"),
      },
      {
        id: "deadLetteredAt",
        headerKey: "arch.events.dead_letter.col.dead_lettered_at",
        cell: (row) => <time dateTime={row.deadLetteredAt}>{when.format(new Date(row.deadLetteredAt))}</time>,
      },
      {
        id: "actions",
        headerKey: "arch.events.dead_letter.col.actions",
        cell: (row) => (
          <span className="platform-events__actions">
            <Button
              variant="secondary"
              aria-label={t("arch.events.dead_letter.retry_row", { id: row.id })}
              disabled={retry.isPending}
              onClick={() => void onRetry(row)}
            >
              {t("arch.events.dead_letter.retry")}
            </Button>
            <Button
              variant="secondary"
              aria-label={t("arch.events.dead_letter.discard_row", { id: row.id })}
              onClick={() => setDiscarding(row)}
            >
              {t("arch.events.dead_letter.discard")}
            </Button>
          </span>
        ),
      },
  ];

  const bulkActions: BulkAction<DeadLetter>[] = [
    {
      id: "retry",
      labelKey: "arch.events.dead_letter.retry_selected",
      permission: EVENTS_MANAGE,
      run: (rows) => void onRetryMany(rows),
    },
  ];

  return (
    <section className="aip-page" aria-labelledby="platform-dead-letter-title">
      <h1 id="platform-dead-letter-title">{t("arch.events.dead_letter.title")}</h1>
      <p>{t("arch.events.dead_letter.intro")}</p>
      <RegisterTable
        id="platform-dead-letter"
        captionKey="arch.events.dead_letter.caption"
        columns={columns}
        query={query}
        onQueryChange={onQueryChange}
        useQuery={useDeadLetters}
        rowId={(row) => row.id}
        bulkActions={bulkActions}
        permissions={permissions}
        search={false}
        translate={t}
      />
      <DiscardDialog
        open={discarding !== null}
        eventId={discarding?.id ?? ""}
        busy={discard.isPending}
        onOpenChange={(open) => !open && setDiscarding(null)}
        onSubmit={(reason) => void onDiscard(reason)}
      />
    </section>
  );
}
