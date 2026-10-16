/**
 * Standard empty, loading and error states (DESIGN-04), plus the offline and sync-conflict
 * variants the field and offline work uses. All text arrives as term keys through `translate`.
 */
import { useState, type ReactNode } from "react";
import { Button } from "../components/button";
import { Icon, type IconName } from "../components/icon";
import { Spinner } from "../components/spinner";
import type { Translate } from "../register/types";

export interface StateAction {
  labelKey: string;
  onSelect: () => void;
}

export interface EmptyStateProps {
  icon: IconName;
  titleKey: string;
  bodyKey: string;
  action?: StateAction;
  translate: Translate;
}

export function EmptyState({ icon, titleKey, bodyKey, action, translate }: EmptyStateProps) {
  return (
    <div className="aip-state aip-state--empty">
      <Icon name={icon} size={32} className="aip-state__icon" />
      <p className="aip-state__title">{translate(titleKey)}</p>
      <p className="aip-state__body">{translate(bodyKey)}</p>
      {action && <Button onClick={action.onSelect}>{translate(action.labelKey)}</Button>}
    </div>
  );
}

export interface LoadingStateProps {
  variant: "skeleton" | "spinner";
  /** Skeleton rows (default 3). */
  rows?: number;
  translate: Translate;
}

export function LoadingState({ variant, rows = 3, translate }: LoadingStateProps) {
  if (variant === "spinner") {
    return (
      <div className="aip-state aip-state--loading" aria-busy="true">
        <Spinner label={translate("ui.loading")} size={24} />
      </div>
    );
  }
  return (
    <div className="aip-state--skeleton" aria-busy="true">
      <span className="aip-visually-hidden" role="status">
        {translate("ui.loading")}
      </span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="aip-state__skeleton-row" aria-hidden="true" />
      ))}
    </div>
  );
}

/** What ErrorState needs from a failed request. */
export interface RequestError {
  status?: number;
  /** The response's `X-Request-Id`, shown so support can find the request. */
  requestId?: string | null;
}

/** Reads the status and correlation id from a failed `Response`. */
export function requestErrorFrom(response: Response): RequestError {
  return { status: response.status, requestId: response.headers.get("X-Request-Id") };
}

/** The term key for an HTTP status: 403, 404 and 409 have their own text; the rest are generic. */
export function errorTermKey(status: number | undefined): string {
  switch (status) {
    case 403:
      return "ui.error.forbidden";
    case 404:
      return "ui.error.notFound";
    case 409:
      return "ui.error.conflict";
    default:
      return "ui.error.generic";
  }
}

export interface ErrorStateProps {
  error: RequestError;
  onRetry: () => void;
  translate: Translate;
}

export function ErrorState({ error, onRetry, translate }: ErrorStateProps) {
  const key = errorTermKey(error.status);
  const [copied, setCopied] = useState(false);
  const { requestId } = error;

  return (
    <div className="aip-state aip-state--error" role="alert">
      <Icon name="alert" size={32} className="aip-state__icon" />
      <p className="aip-state__title">{translate(key)}</p>
      <p className="aip-state__body">{translate(`${key}.body`)}</p>
      {requestId && (
        <p className="aip-state__reference">
          <span>{translate("ui.error.reference")}</span> <code className="aip-state__request-id">{requestId}</code>{" "}
          <Button
            variant="ghost"
            onClick={() => {
              void navigator.clipboard?.writeText(requestId).then(() => setCopied(true));
            }}
          >
            {translate("ui.error.copy")}
          </Button>
          {copied && <span role="status">{translate("ui.error.copied")}</span>}
        </p>
      )}
      <Button variant="secondary" onClick={onRetry}>
        {translate("ui.error.retry")}
      </Button>
    </div>
  );
}

export interface OfflineStateProps {
  onRetry?: () => void;
  translate: Translate;
}

export function OfflineState({ onRetry, translate }: OfflineStateProps) {
  return (
    <div className="aip-state aip-state--offline" role="status">
      <Icon name="warning" size={32} className="aip-state__icon" />
      <p className="aip-state__title">{translate("ui.offline.title")}</p>
      <p className="aip-state__body">{translate("ui.offline.body")}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          {translate("ui.error.retry")}
        </Button>
      )}
    </div>
  );
}

export interface SyncConflictStateProps {
  /** This device's version of the record. */
  mine: ReactNode;
  /** The server's version. */
  theirs: ReactNode;
  onKeepMine: () => void;
  onKeepTheirs: () => void;
  /** Offered only when the record type supports merging. */
  onMerge?: () => void;
  translate: Translate;
}

export function SyncConflictState({ mine, theirs, onKeepMine, onKeepTheirs, onMerge, translate }: SyncConflictStateProps) {
  return (
    <div className="aip-state aip-state--conflict">
      <Icon name="warning" size={32} className="aip-state__icon" />
      <p className="aip-state__title">{translate("ui.conflict.title")}</p>
      <p className="aip-state__body">{translate("ui.conflict.body")}</p>
      <div className="aip-state__versions">
        <section aria-label={translate("ui.conflict.mine")} className="aip-state__version">
          <p className="aip-state__version-title">{translate("ui.conflict.mine")}</p>
          {mine}
        </section>
        <section aria-label={translate("ui.conflict.theirs")} className="aip-state__version">
          <p className="aip-state__version-title">{translate("ui.conflict.theirs")}</p>
          {theirs}
        </section>
      </div>
      <div className="aip-state__actions">
        <Button onClick={onKeepMine}>{translate("ui.conflict.keepMine")}</Button>
        <Button variant="secondary" onClick={onKeepTheirs}>
          {translate("ui.conflict.keepTheirs")}
        </Button>
        {onMerge && (
          <Button variant="secondary" onClick={onMerge}>
            {translate("ui.conflict.merge")}
          </Button>
        )}
      </div>
    </div>
  );
}
