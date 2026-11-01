/**
 * Invite an external user (PORTAL-07) through PORTAL-01's `POST /admin/portal/users`: identity
 * (email, name, company) and 1 to 20 grants from the grant builder. The inviting project admin is the
 * only approval and each grant's expiry is its project's access period, so the form has neither an
 * approver nor an expiry (ADR 0036).
 *
 * Validated by the Zod schema orval generates from the API (`schemas.PortalUsersInviteBody`); the
 * server's answers land on their inputs (an email code on Email, `PROJECT_CLOSED` / `ASSET_NOT_FOUND`
 * / `GRANT_EXISTS` on the grant row they name). Inviting needs a fresh second factor: a 401
 * `STEP_UP_REQUIRED` keeps the form in session storage, sends the browser to the step-up, and on
 * return refills the form and offers to send it again (IDENTITY-04).
 */
import { getPortalUsersListQueryKey, schemas, usePortalUsersInvite, type InviteIn } from "@aip/api-client";
import { Button, FormField, Input } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { startStepUp, takePendingStepUp } from "../identity/step-up";
import { t } from "../shell/t";
import { apiError, EMAIL_CODES, errorMessage } from "./errors";
import { useProjects } from "./format";
import { emptyGrant, GrantRow, MAX_GRANTS, toGrantIn, type GrantDraft } from "./GrantBuilder";
import { INVITE } from "./PortalUsersRegister";

export const INVITE_STEP_UP_KEY = "portal-invite";

type Field = "email" | "firstName" | "lastName" | "companyName";
const FIELDS: readonly Field[] = ["email", "firstName", "lastName", "companyName"];
const FIELD_MESSAGE: Record<Field, string> = {
  email: "portal.error.invalid_email",
  firstName: "portal.admin.field.first_name_error",
  lastName: "portal.admin.field.last_name_error",
  companyName: "portal.admin.field.company_error",
};

interface FormState {
  email: string;
  firstName: string;
  lastName: string;
  companyName: string;
  grants: GrantDraft[];
}

type GrantErrors = Record<number, { project?: string; asset?: string; row?: string }>;

function initialState(): FormState {
  return { email: "", firstName: "", lastName: "", companyName: "", grants: [emptyGrant()] };
}

function toBody(state: FormState): InviteIn {
  return {
    email: state.email.trim(),
    firstName: state.firstName.trim(),
    lastName: state.lastName.trim(),
    companyName: state.companyName.trim(),
    grants: state.grants.map(toGrantIn),
  };
}

export interface InviteFormProps {
  permissions: readonly string[];
  onInvited: (portalUserId: string) => void;
}

export function InviteForm({ permissions, onInvited }: InviteFormProps) {
  const [denied, setDenied] = useState(!permissions.includes(INVITE));
  // Back from a step-up: the saved form, once, with an offer to send it again.
  const [resumed] = useState(() => takePendingStepUp<FormState>(INVITE_STEP_UP_KEY));
  const [state, setState] = useState<FormState>(() => resumed ?? initialState());
  const [retryOffered, setRetryOffered] = useState(resumed !== null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<Field, string>>>({});
  const [grantErrors, setGrantErrors] = useState<GrantErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const { projects } = useProjects();
  const queryClient = useQueryClient();
  const invite = usePortalUsersInvite();

  if (denied) {
    return (
      <section className="portal-admin" aria-labelledby="portal-invite-denied">
        <h1 id="portal-invite-denied">{t("portal.admin.denied.title")}</h1>
        <p>{t("portal.admin.denied.body")}</p>
        <Link to="/admin/portal/users">{t("portal.admin.back")}</Link>
      </section>
    );
  }

  const set = (patch: Partial<FormState>) => setState((s) => ({ ...s, ...patch }));
  const setGrant = (index: number, next: GrantDraft) =>
    setState((s) => ({ ...s, grants: s.grants.map((g, i) => (i === index ? next : g)) }));

  /** Client-side check with the API's own schema; true when the body may be sent. */
  function validate(body: InviteIn): boolean {
    const parsed = schemas.PortalUsersInviteBody.safeParse(body);
    if (parsed.success) return true;
    const fields: Partial<Record<Field, string>> = {};
    const grants: GrantErrors = {};
    for (const issue of parsed.error.issues) {
      const [head, index, key] = issue.path;
      if (typeof head === "string" && (FIELDS as readonly string[]).includes(head)) {
        fields[head as Field] = t(FIELD_MESSAGE[head as Field]);
      } else if (head === "grants" && typeof index === "number") {
        const row = (grants[index] ??= {});
        if (key === "projectId") row.project = t("portal.admin.grant.project_error");
        else if (key === "assetId") row.asset = t("portal.error.asset_not_found");
      }
    }
    setFieldErrors(fields);
    setGrantErrors(grants);
    return false;
  }

  /** Put a 409/422 answer on the input it names; false when nothing could be placed. */
  function placeServerError(data: unknown): boolean {
    const error = apiError(data);
    if (error) {
      if (EMAIL_CODES.has(error.code)) {
        setFieldErrors({ email: errorMessage(error.code, null) });
        return true;
      }
      const index = state.grants.findIndex((g) =>
        error.assetId ? g.assetId === error.assetId : error.projectId ? g.projectId === error.projectId : false,
      );
      if (index >= 0) {
        const message = errorMessage(error.code, null);
        setGrantErrors({ [index]: error.code === "ASSET_NOT_FOUND" ? { asset: message } : { project: message } });
        return true;
      }
      if (error.code === "GRANT_EXISTS") {
        setFormError(errorMessage(error.code, null));
        return true;
      }
      return false;
    }
    // FastAPI's 422: `detail[].loc` = ["body", field] or ["body", "grants", i, key].
    const detail = (data as { detail?: unknown } | null)?.detail;
    if (!Array.isArray(detail)) return false;
    const fields: Partial<Record<Field, string>> = {};
    const grants: GrantErrors = {};
    for (const item of detail as { loc?: unknown }[]) {
      const loc = Array.isArray(item.loc) ? item.loc : [];
      const [, head, index, key] = loc as unknown[];
      if (typeof head === "string" && (FIELDS as readonly string[]).includes(head)) fields[head as Field] = t(FIELD_MESSAGE[head as Field]);
      else if (head === "grants" && typeof index === "number") {
        (grants[index] ??= {})[key === "assetId" ? "asset" : key === "projectId" ? "project" : "row"] = t("portal.admin.grant.row_error");
      }
    }
    setFieldErrors(fields);
    setGrantErrors(grants);
    return Object.keys(fields).length > 0 || Object.keys(grants).length > 0;
  }

  async function send() {
    setFormError(null);
    setRetryOffered(false);
    const body = toBody(state);
    if (!validate(body)) return;
    setFieldErrors({});
    setGrantErrors({});
    const response = await invite.mutateAsync({ data: body });
    if (response.status === 201) {
      await queryClient.invalidateQueries({ queryKey: getPortalUsersListQueryKey().slice(0, 1) });
      onInvited(response.data.id);
      return;
    }
    const status = response.status as number;
    if (status === 401 && startStepUp(response, { key: INVITE_STEP_UP_KEY, state })) return;
    if (status === 403) {
      setDenied(true);
      return;
    }
    if (!placeServerError(response.data as unknown)) {
      setFormError(errorMessage(apiError(response.data)?.code, response.headers.get("x-request-id")));
    }
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void send();
  };

  const errorOf = (field: Field): { error?: string } => (fieldErrors[field] ? { error: fieldErrors[field] } : {});

  return (
    <section className="portal-admin portal-admin--form" aria-labelledby="portal-invite-title">
      <h1 id="portal-invite-title">{t("portal.admin.invite_title")}</h1>
      <p className="portal-admin__meta">{t("portal.admin.invite_intro")}</p>
      {retryOffered ? (
        <div className="portal-admin__notice" role="status">
          <p>{t("identity.stepUp.retryPrompt")}</p>
          <Button type="button" onClick={() => void send()}>
            {t("identity.stepUp.retry")}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setRetryOffered(false)}>
            {t("identity.stepUp.dismiss")}
          </Button>
        </div>
      ) : null}
      <form noValidate onSubmit={onSubmit}>
        <FormField label={t("portal.admin.field.email")} {...errorOf("email")}>
          {(control) => (
            <Input {...control} type="email" autoComplete="off" value={state.email} onChange={(e) => set({ email: e.target.value })} />
          )}
        </FormField>
        <FormField label={t("portal.admin.field.first_name")} {...errorOf("firstName")}>
          {(control) => <Input {...control} value={state.firstName} onChange={(e) => set({ firstName: e.target.value })} />}
        </FormField>
        <FormField label={t("portal.admin.field.last_name")} {...errorOf("lastName")}>
          {(control) => <Input {...control} value={state.lastName} onChange={(e) => set({ lastName: e.target.value })} />}
        </FormField>
        <FormField label={t("portal.admin.field.company")} {...errorOf("companyName")}>
          {(control) => <Input {...control} value={state.companyName} onChange={(e) => set({ companyName: e.target.value })} />}
        </FormField>

        <h2 className="portal-admin__subtitle">{t("portal.admin.grants_title")}</h2>
        <p className="portal-admin__meta">{t("portal.admin.grants_intro")}</p>
        {state.grants.map((grant, index) => (
          <GrantRow
            key={grant.key}
            index={index}
            value={grant}
            projects={projects}
            onChange={(next) => setGrant(index, next)}
            onRemove={state.grants.length > 1 ? () => set({ grants: state.grants.filter((_, i) => i !== index) }) : undefined}
            errors={grantErrors[index]}
          />
        ))}
        {state.grants.length < MAX_GRANTS ? (
          <Button type="button" variant="secondary" onClick={() => set({ grants: [...state.grants, emptyGrant()] })}>
            {t("portal.admin.grant.add")}
          </Button>
        ) : null}

        {formError ? (
          <p role="alert" className="aip-form-field__error">
            {formError}
          </p>
        ) : null}
        <div className="portal-admin__actions">
          <Button type="submit" disabled={invite.isPending}>
            {invite.isPending ? t("portal.admin.invite_sending") : t("portal.admin.invite_submit")}
          </Button>
          <Button variant="ghost" asChild>
            <Link to="/admin/portal/users">{t("portal.admin.cancel")}</Link>
          </Button>
        </div>
      </form>
    </section>
  );
}
