/**
 * Plan and usage (ENT-01, ADR 0008/0017): the tenant's plan, term, renewal date and contract
 * reference, seats and storage used against each limit, and the features the plan includes.
 * Read-only: there is no plan change, invoice or payment control (sales-led; operators change plans).
 * Every label is a terminology key; plan, term and status codes map to `tenancy.plan.*` keys.
 */
import { useTenancyPlanAndUsage, type LimitOut, type PlanAndUsage } from "@aip/api-client";
import { Spinner, Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@aip/ui";
import { t } from "../shell/t";

function day(value: string): string {
  // Dates are calendar dates (no time zone): format the parts, never via the local clock.
  const [year, month, date] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("en-AU", { dateStyle: "long", timeZone: "UTC" }).format(
    new Date(Date.UTC(year!, (month ?? 1) - 1, date ?? 1)),
  );
}

function month(value: string): string {
  const [year, monthNumber] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("en-AU", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(year!, (monthNumber ?? 1) - 1, 1)),
  );
}

function amount(value: number): string {
  return new Intl.NumberFormat("en-AU", { maximumFractionDigits: 2 }).format(value);
}

function limitLabel(limit: LimitOut): string {
  return t(`tenancy.${limit.key}`);
}

function Summary({ plan }: { plan: PlanAndUsage }) {
  const rows: [string, string][] = [
    [t("tenancy.plan.plan"), plan.plan ? t(`tenancy.plan.code.${plan.plan}`) : t("tenancy.plan.not_set")],
    [t("tenancy.plan.term"), plan.term ? t(`tenancy.plan.term.${plan.term}`) : t("tenancy.plan.not_set")],
    [t("tenancy.plan.status"), plan.status ? t(`tenancy.plan.status.${plan.status}`) : t("tenancy.plan.not_set")],
    [t("tenancy.plan.renewal"), plan.renewalDate ? day(plan.renewalDate) : t("tenancy.plan.not_set")],
    [t("tenancy.plan.contract"), plan.contractRef ?? t("tenancy.plan.not_set")],
  ];
  return (
    <section aria-labelledby="plan-summary">
      <h2 id="plan-summary">{t("tenancy.plan.summary")}</h2>
      <dl className="aip-plan-summary">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Limits({ plan }: { plan: PlanAndUsage }) {
  return (
    <section aria-labelledby="plan-usage">
      <h2 id="plan-usage">{t("tenancy.plan.usage")}</h2>
      <p>
        {plan.usagePeriod ? t("tenancy.plan.usage_period", { period: month(plan.usagePeriod) }) : t("tenancy.plan.usage_none")}
      </p>
      <Table>
        <TableCaption>{t("tenancy.plan.usage")}</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">{t("tenancy.plan.col.item")}</TableHead>
            <TableHead scope="col">{t("tenancy.plan.col.used")}</TableHead>
            <TableHead scope="col">{t("tenancy.plan.col.limit")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {plan.limits.map((limit) => (
            <TableRow key={limit.key}>
              <TableHead scope="row">{limitLabel(limit)}</TableHead>
              <TableCell>{limit.used == null ? t("tenancy.plan.not_measured") : amount(limit.used)}</TableCell>
              <TableCell>{limit.limit == null ? t("tenancy.plan.unlimited") : amount(limit.limit)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {plan.dbEstimate && <p>{t("tenancy.plan.db_estimate", { method: plan.dbEstimate.method })}</p>}
    </section>
  );
}

function Features({ plan }: { plan: PlanAndUsage }) {
  return (
    <section aria-labelledby="plan-features">
      <h2 id="plan-features">{t("tenancy.plan.features")}</h2>
      <Table>
        <TableCaption>{t("tenancy.plan.features")}</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">{t("tenancy.plan.col.item")}</TableHead>
            <TableHead scope="col">{t("tenancy.plan.col.status")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {plan.features.map((feature) => (
            <TableRow key={feature.key}>
              <TableHead scope="row">{t(`tenancy.${feature.key}`)}</TableHead>
              <TableCell>{feature.enabled ? t("tenancy.plan.included") : t("tenancy.plan.not_included")}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}

export function PlanAndUsagePage() {
  const query = useTenancyPlanAndUsage();
  const plan = query.data?.status === 200 ? query.data.data : undefined;
  return (
    <section className="aip-page" aria-labelledby="plan-title">
      <h1 id="plan-title">{t("tenancy.plan.title")}</h1>
      <p>{t("tenancy.plan.intro")}</p>
      {query.isPending ? (
        <p role="status">
          <Spinner label={t("tenancy.plan.loading")} />
        </p>
      ) : !plan ? (
        <p role="alert">{t("tenancy.plan.error")}</p>
      ) : (
        <>
          {plan.plan === null && <p role="status">{t("tenancy.plan.none")}</p>}
          <Summary plan={plan} />
          <Limits plan={plan} />
          <Features plan={plan} />
        </>
      )}
    </section>
  );
}
