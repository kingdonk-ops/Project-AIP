import {
  Button,
  ErrorState,
  LoadingState,
  RecordDetail,
  confirm,
  requestErrorFrom,
  toast,
  type RequestError,
  type Translate,
} from "@aip/ui";
import { useQuery } from "@tanstack/react-query";
import { t } from "../../features/shell/t";

/**
 * DESIGN-04 dev-only fixture: a record detail page for the Playwright run (danger confirm, toast,
 * ErrorState with the correlation id and Retry). Loaded lazily by router.ts only when
 * `!import.meta.env.PROD`. Fixture strings are test data, so they are not dictionary keys; the
 * confirm dialog and toast (mounted in __root with the app's `t`) use the shared `ui.*` keys.
 */

export const RECORD_FIXTURE_API = "/api/v1/__fixtures/record";

const fixtureText: Record<string, string> = {
  "fixture.status.open": "Open",
  "fixture.step.open": "Open",
  "fixture.step.closed": "Closed",
  "fixture.action.close": "Close out",
};

const translate: Translate = (key, params) => fixtureText[key] ?? t(key, params);

class FixtureError extends Error {
  constructor(readonly detail: RequestError) {
    super("fixture request failed");
  }
}

async function fetchRecord(): Promise<{ summary: string }> {
  const response = await fetch(RECORD_FIXTURE_API);
  if (!response.ok) throw new FixtureError(requestErrorFrom(response));
  return (await response.json()) as { summary: string };
}

export function RecordFixture() {
  const query = useQuery({ queryKey: ["fixture", "record"], queryFn: fetchRecord, retry: false });

  async function remove() {
    const ok = await confirm({
      titleKey: "ui.delete.title",
      bodyKey: "ui.delete.body",
      confirmKey: "ui.delete.confirm",
      params: { code: "NCR-0042" },
      tone: "danger",
    });
    if (ok) toast.success("ui.delete.done", { code: "NCR-0042" });
  }

  const details =
    query.isPending || (query.isError && query.isFetching) ? (
      <LoadingState variant="skeleton" translate={translate} />
    ) : query.isError ? (
      <ErrorState
        error={query.error instanceof FixtureError ? query.error.detail : {}}
        onRetry={() => void query.refetch()}
        translate={translate}
      />
    ) : (
      <p data-testid="record-summary">{query.data.summary}</p>
    );

  return (
    <main data-testid="record-fixture" style={{ maxWidth: 1200, margin: "0 auto", padding: 16 }}>
      <RecordDetail
        id="NCR-0042"
        title="Cracked lagging on line 12"
        breadcrumb={<span>{"Plant / Unit 2 / Line 12"}</span>}
        status={{ tone: "warning", icon: "warning", labelKey: "fixture.status.open" }}
        workflow={{
          steps: [
            { id: "open", labelKey: "fixture.step.open" },
            { id: "closed", labelKey: "fixture.step.closed" },
          ],
          current: "open",
          actions: [{ id: "close", labelKey: "fixture.action.close", onSelect: () => {} }],
        }}
        tabs={[
          { id: "details", content: details },
          { id: "linked", content: <p>{"No linked records"}</p> },
          { id: "documents", content: <p>{"No documents"}</p> },
          { id: "history", content: <p>{"Created by Alice"}</p> },
        ]}
        rightRail={{ comments: <p>{"No comments"}</p>, attachments: <p>{"No attachments"}</p> }}
        actions={
          <Button variant="danger" onClick={() => void remove()}>
            {"Delete"}
          </Button>
        }
        railKey="fixture"
        translate={translate}
      />
    </main>
  );
}
