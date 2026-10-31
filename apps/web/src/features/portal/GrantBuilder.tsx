/**
 * The grant builder (PORTAL-07): one row per grant of project (draft or active projects only), an
 * optional asset subtree (ASSETS-03's `ParentPicker`, "Whole project" when empty) and the actions.
 * View is always on (PORTAL-01: every grant includes it). There is no expiry: each grant lasts for
 * its project's access period (`portal_access_days`).
 */
import type { GrantIn, GrantInActionsItem, ProjectOut } from "@aip/api-client";
import { Button, Checkbox, FormField } from "@aip/ui";
import { useId } from "react";
import { ParentPicker } from "../assets/ParentPicker";
import { t } from "../shell/t";

export const GRANT_ACTIONS = ["view", "sign_off", "witness", "download"] as const satisfies readonly GrantInActionsItem[];
export const MAX_GRANTS = 20;
const OPEN_PROJECT_STATUSES: ReadonlySet<string> = new Set(["draft", "active"]);

export interface GrantDraft {
  /** Local row key (not sent). */
  key: string;
  projectId: string;
  /** `""` is the whole project. */
  assetId: string;
  actions: GrantInActionsItem[];
}

let nextKey = 0;

export function emptyGrant(): GrantDraft {
  nextKey += 1;
  return { key: `grant-${nextKey}`, projectId: "", assetId: "", actions: ["view"] };
}

/** The API body of a draft row (actions in the API's order). */
export function toGrantIn(draft: GrantDraft): GrantIn {
  return {
    projectId: draft.projectId,
    ...(draft.assetId ? { assetId: draft.assetId } : {}),
    actions: GRANT_ACTIONS.filter((a) => draft.actions.includes(a)),
  };
}

/** Projects a grant can be given on. */
export function openProjects(projects: readonly ProjectOut[]): ProjectOut[] {
  return projects.filter((p) => OPEN_PROJECT_STATUSES.has(p.status));
}

export interface GrantRowProps {
  index: number;
  value: GrantDraft;
  projects: readonly ProjectOut[];
  onChange: (next: GrantDraft) => void;
  /** Omitted: the row cannot be removed (the only row). */
  onRemove?: (() => void) | undefined;
  /** Errors on this row's project or asset (already translated). */
  errors?: { project?: string | undefined; asset?: string | undefined; row?: string | undefined } | undefined;
}

export function GrantRow({ index, value, projects, onChange, onRemove, errors }: GrantRowProps) {
  const legendId = useId();
  const toggle = (action: GrantInActionsItem, on: boolean) =>
    onChange({ ...value, actions: on ? [...value.actions, action] : value.actions.filter((a) => a !== action) });

  return (
    <fieldset className="portal-grant" aria-labelledby={legendId}>
      <legend id={legendId} className="portal-grant__legend">
        {t("portal.admin.grant.legend", { number: index + 1 })}
      </legend>
      <FormField label={t("portal.admin.grant.project")} {...(errors?.project ? { error: errors.project } : {})}>
        {(control) => (
          <select
            {...control}
            className="portal-admin__select"
            value={value.projectId}
            onChange={(e) => onChange({ ...value, projectId: e.target.value })}
          >
            <option value="">{t("portal.admin.grant.project_choose")}</option>
            {openProjects(projects).map((p) => (
              <option key={p.id} value={p.id}>
                {`${p.code} ${p.name}`}
              </option>
            ))}
          </select>
        )}
      </FormField>
      <FormField
        label={t("portal.admin.grant.asset")}
        hint={t("portal.admin.grant.asset_hint")}
        {...(errors?.asset ? { error: errors.asset } : {})}
      >
        {(control) => (
          <ParentPicker
            id={control.id}
            label={t("portal.admin.grant.asset")}
            value={value.assetId}
            onChange={(assetId) => onChange({ ...value, assetId })}
            topLevelLabel={t("portal.admin.grant.asset_whole")}
            placeholder={t("portal.admin.grant.asset_search")}
          />
        )}
      </FormField>
      <div role="group" aria-label={t("portal.admin.grant.actions")} className="portal-grant__actions">
        <span className="portal-grant__actions-label">{t("portal.admin.grant.actions")}</span>
        {GRANT_ACTIONS.map((action) => {
          const id = `${legendId}-${action}`;
          return (
            <span key={action} className="portal-grant__action">
              <Checkbox
                id={id}
                checked={action === "view" || value.actions.includes(action)}
                disabled={action === "view"}
                onCheckedChange={(checked) => toggle(action, checked === true)}
              />
              <label htmlFor={id}>{t(`portal.grant.action.${action}`)}</label>
            </span>
          );
        })}
      </div>
      {errors?.row ? (
        <p role="alert" className="aip-form-field__error">
          {errors.row}
        </p>
      ) : null}
      {onRemove ? (
        <Button type="button" variant="ghost" onClick={onRemove}>
          {t("portal.admin.grant.remove", { number: index + 1 })}
        </Button>
      ) : null}
    </fieldset>
  );
}
