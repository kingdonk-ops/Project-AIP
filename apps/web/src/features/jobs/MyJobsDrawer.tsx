import {
  getJobsListMineQueryKey,
  useJobsCancel,
  useJobsListMine,
  useJobsRetry,
  type JobOut,
  type JobStatus,
} from "@aip/api-client";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  EmptyState,
  ErrorState,
  Icon,
  LoadingState,
  Spinner,
  StatusChip,
  toast,
  type IconName,
  type StatusTone,
} from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { t } from "../shell/t";

/**
 * OPS-03: the caller's background jobs in a side drawer, opened from the header. Filter chips
 * narrow by status; active jobs refresh every few seconds and can be cancelled; failed jobs show
 * their error and correlation id and can be retried. All calls go through the generated client.
 */

export const ACTIVE_REFRESH_MS = 3000;

const FILTERS = {
  all: [],
  active: ["queued", "running"],
  failed: ["failed"],
  done: ["succeeded", "cancelled"],
} as const satisfies Record<string, readonly JobStatus[]>;
type Filter = keyof typeof FILTERS;

const LOOK: Record<JobStatus, { tone: StatusTone; icon: IconName }> = {
  queued: { tone: "neutral", icon: "clock" },
  running: { tone: "info", icon: "loader" },
  succeeded: { tone: "success", icon: "success" },
  failed: { tone: "danger", icon: "alert" },
  cancelled: { tone: "neutral", icon: "minus" },
};

function isActive(job: JobOut) {
  return job.status === "queued" || job.status === "running";
}

export interface MyJobsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MyJobsDrawer({ open, onOpenChange }: MyJobsDrawerProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const params = { limit: 20, ...(FILTERS[filter].length ? { status: [...FILTERS[filter]] } : {}) };
  const list = useJobsListMine(params, {
    query: {
      enabled: open,
      refetchInterval: (query) => {
        const res = query.state.data;
        return res?.status === 200 && res.data.items.some(isActive) ? ACTIVE_REFRESH_MS : false;
      },
    },
  });
  const items = list.data?.status === 200 ? list.data.data.items : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="jobs-drawer" closeLabel={t("ui.close")}>
        <DialogTitle>{t("ops.jobs.title")}</DialogTitle>
        <DialogDescription>{t("ops.jobs.description")}</DialogDescription>
        <div className="jobs-drawer__filters" role="group" aria-label={t("ops.jobs.filters")}>
          {(Object.keys(FILTERS) as Filter[]).map((key) => (
            <Button
              key={key}
              variant={filter === key ? "primary" : "secondary"}
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
            >
              {t(`ops.jobs.filter.${key}`)}
            </Button>
          ))}
        </div>
        {list.isPending ? (
          <LoadingState variant="skeleton" rows={3} translate={t} />
        ) : list.isError || list.data?.status !== 200 ? (
          <ErrorState error={{}} onRetry={() => void list.refetch()} translate={t} />
        ) : items.length === 0 ? (
          <EmptyState icon="clock" titleKey="ops.jobs.empty.title" bodyKey="ops.jobs.empty.body" translate={t} />
        ) : (
          <ul className="jobs-drawer__list">
            {items.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}

function JobRow({ job }: { job: JobOut }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: getJobsListMineQueryKey().slice(0, 1) });
  const after = (done: string) => (res: { status: number }) => {
    if (res.status === 200 || res.status === 201) toast.success(done);
    else if (res.status === 409) toast.info("ops.jobs.alreadyFinished");
    else toast.error("ops.jobs.actionFailed");
    void refresh();
  };
  const cancel = useJobsCancel({ mutation: { onSuccess: after("ops.jobs.cancelled") } });
  const retry = useJobsRetry({ mutation: { onSuccess: after("ops.jobs.retried") } });
  const look = LOOK[job.status];
  const started = new Date(job.createdAt).toLocaleString("en-AU", { dateStyle: "medium", timeStyle: "short" });

  return (
    <li className="jobs-drawer__item" data-testid="job-row" data-status={job.status}>
      <div className="jobs-drawer__head">
        <span className="jobs-drawer__name">{t("ops.jobs.item")}</span>
        <StatusChip tone={look.tone} icon={look.icon} label={t(`ops.jobs.status.${job.status}`)} />
      </div>
      <p className="jobs-drawer__meta">{t("ops.jobs.started", { time: started })}</p>
      {job.status === "running" ? <Spinner label={t("ops.jobs.running")} /> : null}
      {job.status === "failed" ? (
        <p className="jobs-drawer__error">
          {job.error ? <span>{job.error}</span> : null}{" "}
          <span>{t("ops.jobs.reference")}</span> <code className="jobs-drawer__ref">{job.correlationId}</code>
        </p>
      ) : null}
      <div className="jobs-drawer__actions">
        {isActive(job) ? (
          <Button variant="secondary" disabled={cancel.isPending} onClick={() => cancel.mutate({ jobId: job.id })}>
            {t("ops.jobs.cancel")}
          </Button>
        ) : null}
        {job.status === "failed" ? (
          <Button variant="secondary" disabled={retry.isPending} onClick={() => retry.mutate({ jobId: job.id })}>
            {t("ops.jobs.retry")}
          </Button>
        ) : null}
        {job.status === "succeeded" && job.resultRef?.startsWith("/") ? (
          <Button asChild variant="secondary">
            <a href={job.resultRef}>{t("ops.jobs.openResult")}</a>
          </Button>
        ) : null}
      </div>
    </li>
  );
}

/** The header button that opens the drawer. */
export function JobsButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="ghost" size="icon" aria-label={t("ops.jobs.open")} onClick={() => setOpen(true)}>
        <Icon name="clock" size={20} />
      </Button>
      <MyJobsDrawer open={open} onOpenChange={setOpen} />
    </>
  );
}
