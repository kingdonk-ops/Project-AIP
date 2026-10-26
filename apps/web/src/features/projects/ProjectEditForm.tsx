/**
 * Edit a project (PROJECTS-07) on the detail page's Details tab. Like `ProjectCreateForm`, the body
 * is validated by the Zod schema orval generates from the API's OpenAPI document
 * (`schemas.ProjectsUpdateBody`), so the Pydantic model in PROJECTS-01 stays the source of truth.
 * The edit is optimistic-concurrency safe: it sends the `syncVersion` the client last read, and a
 * 409 tells the user the project changed underneath them. Without `project.update` the fields are
 * read-only; the server also enforces it (and `project.archive` for the archived status).
 */
import {
  getProjectsGetQueryKey,
  getProjectsListQueryKey,
  schemas,
  useProjectsUpdate,
  type ProjectOut,
  type ProjectUpdate,
  type SiteOut,
} from "@aip/api-client";
import { Button, FormField, Input, toast } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, type FieldPath, type UseFormSetError } from "react-hook-form";
import { t } from "../shell/t";
import { PROJECT_STATUSES, type ProjectStatus } from "./search";

type Field = "code" | "name" | "status" | "siteId" | "region" | "timezone" | "currency";
const FIELDS: readonly Field[] = ["code", "name", "status", "siteId", "region", "timezone", "currency"];

const FIELD_MESSAGE: Record<Field, string> = {
  code: "projects.error.code",
  name: "projects.error.name",
  status: "projects.error.invalid",
  siteId: "projects.error.site",
  region: "projects.error.region",
  timezone: "projects.error.timezone",
  currency: "projects.error.currency",
};
const DOMAIN_ERRORS: Record<string, [Field, string]> = {
  PROJECT_CODE_TAKEN: ["code", "projects.error.code_taken"],
  REGION_UNKNOWN: ["region", "projects.error.region"],
  SITE_NOT_FOUND: ["siteId", "projects.error.site"],
};

interface FormValues {
  code: string;
  name: string;
  status: ProjectStatus;
  siteId: string;
  region: string;
  timezone: string;
  currency: string;
}

function initialValues(project: ProjectOut): FormValues {
  return {
    code: project.code,
    name: project.name,
    status: project.status,
    siteId: project.siteId ?? "",
    region: project.region ?? "",
    timezone: project.timezone ?? "",
    currency: project.currency ?? "",
  };
}

/** Empty optional fields are cleared (null); the three required fields are always sent. */
function toBody(values: FormValues, syncVersion: number): ProjectUpdate {
  const orNull = (value: string) => (value.trim() === "" ? null : value.trim());
  return {
    syncVersion,
    code: values.code.trim(),
    name: values.name.trim(),
    status: values.status,
    siteId: orNull(values.siteId),
    region: orNull(values.region),
    timezone: orNull(values.timezone),
    currency: orNull(values.currency),
  } as ProjectUpdate;
}

export interface ProjectEditFormProps {
  project: ProjectOut;
  sites: readonly SiteOut[];
  permissions: readonly string[];
}

export function ProjectEditForm({ project, sites, permissions }: ProjectEditFormProps) {
  const canUpdate = permissions.includes("project.update");
  const [formError, setFormError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const update = useProjectsUpdate();
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<FormValues>({ values: initialValues(project) });

  if (!canUpdate) {
    return <ProjectFacts project={project} sites={sites} />;
  }

  const errorOf = (field: Field): { error?: string } => {
    const error = errors[field];
    if (!error) return {};
    return { error: error.type === "server" && error.message ? error.message : t(FIELD_MESSAGE[field]) };
  };

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    const body = toBody(values, project.syncVersion);
    const parsed = schemas.ProjectsUpdateBody.safeParse(body);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        const field = issue.path[0];
        if (typeof field === "string" && (FIELDS as readonly string[]).includes(field)) {
          setError(field as Field, { type: "client", message: t(FIELD_MESSAGE[field as Field]) }, { shouldFocus: true });
        }
      }
      return;
    }
    const response = await update.mutateAsync({ projectId: project.id, data: body });
    if (response.status === 200) {
      await queryClient.invalidateQueries({ queryKey: getProjectsGetQueryKey(project.id) });
      await queryClient.invalidateQueries({ queryKey: getProjectsListQueryKey().slice(0, 1) });
      reset(initialValues(response.data));
      toast.success("projects.detail.edit.saved", { code: response.data.code });
      return;
    }
    if ((response.status as number) === 403) {
      setFormError(t("projects.error.forbidden"));
      return;
    }
    if ((response.status as number) === 409) {
      setFormError(t("projects.error.conflict"));
      return;
    }
    if (!applyEditServerErrors(response.data as unknown, setError)) {
      const id = response.headers.get("x-request-id");
      setFormError(id ? `${t("projects.error.save")} ${t("projects.error.request_id", { id })}` : t("projects.error.save"));
    }
  });

  return (
    <form className="projects-form" noValidate aria-labelledby="projects-edit-title" onSubmit={(e) => void onSubmit(e)}>
      <h2 id="projects-edit-title">{t("projects.detail.edit.title")}</h2>
      <FormField label={t("projects.field.code")} hint={t("projects.field.code_hint")} {...errorOf("code")}>
        {(control) => <Input {...control} autoComplete="off" className="projects-register__mono" {...register("code")} />}
      </FormField>
      <FormField label={t("projects.field.name")} {...errorOf("name")}>
        {(control) => <Input {...control} {...register("name")} />}
      </FormField>
      <FormField label={t("projects.field.status")} {...errorOf("status")}>
        {(control) => (
          <select {...control} className="projects-register__select" {...register("status")}>
            {PROJECT_STATUSES.map((value) => (
              <option key={value} value={value}>
                {t(`projects.status.${value}`)}
              </option>
            ))}
          </select>
        )}
      </FormField>
      <FormField label={t("projects.field.site")} {...errorOf("siteId")}>
        {(control) => (
          <select {...control} className="projects-register__select" {...register("siteId")}>
            <option value="">{t("projects.field.site_none")}</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        )}
      </FormField>
      <FormField label={t("projects.field.region")} hint={t("projects.field.region_hint")} {...errorOf("region")}>
        {(control) => <Input {...control} {...register("region")} />}
      </FormField>
      <FormField label={t("projects.field.timezone")} hint={t("projects.field.timezone_hint")} {...errorOf("timezone")}>
        {(control) => <Input {...control} {...register("timezone")} />}
      </FormField>
      <FormField label={t("projects.field.currency")} hint={t("projects.field.currency_hint")} {...errorOf("currency")}>
        {(control) => <Input {...control} maxLength={3} {...register("currency")} />}
      </FormField>
      {formError ? (
        <p role="alert" className="aip-form-field__error">
          {formError}
        </p>
      ) : null}
      <div className="projects-form__actions">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? t("projects.detail.edit.saving") : t("projects.detail.edit.submit")}
        </Button>
        <Button type="button" variant="ghost" disabled={isSubmitting || !isDirty} onClick={() => reset(initialValues(project))}>
          {t("projects.detail.edit.cancel")}
        </Button>
      </div>
    </form>
  );
}

/** Read-only view of the fields for a user without `project.update`. */
function ProjectFacts({ project, sites }: { project: ProjectOut; sites: readonly SiteOut[] }) {
  const siteName = project.siteId ? (sites.find((s) => s.id === project.siteId)?.name ?? "") : "";
  const rows: [string, string][] = [
    ["projects.field.code", project.code],
    ["projects.field.name", project.name],
    ["projects.field.status", t(`projects.status.${project.status}`)],
    ["projects.field.site", siteName],
    ["projects.field.region", project.region ?? ""],
    ["projects.field.timezone", project.timezone ?? ""],
    ["projects.field.currency", project.currency ?? ""],
  ];
  return (
    <section aria-labelledby="projects-facts-title">
      <h2 id="projects-facts-title">{t("projects.detail.read.title")}</h2>
      <dl className="projects-facts">
        {rows.map(([key, value]) => (
          <div key={key} className="projects-facts__row">
            <dt>{t(key)}</dt>
            <dd className={key === "projects.field.code" ? "projects-register__mono" : undefined}>{value || "—"}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

type SetError = UseFormSetError<FormValues>;

/** Put a 409/422 body's errors on their inputs. Returns false when nothing could be mapped. */
export function applyEditServerErrors(body: unknown, setError: SetError): boolean {
  if (typeof body !== "object" || body === null) return false;
  const record = body as { code?: unknown; detail?: unknown };
  if (typeof record.code === "string" && record.code in DOMAIN_ERRORS) {
    const [field, key] = DOMAIN_ERRORS[record.code]!;
    setError(field, { type: "server", message: t(key) }, { shouldFocus: true });
    return true;
  }
  if (!Array.isArray(record.detail)) return false;
  let mapped = false;
  for (const item of record.detail as { loc?: unknown }[]) {
    const loc = Array.isArray(item.loc) ? item.loc : [];
    const field = loc[0] === "body" ? loc[1] : undefined;
    if (typeof field === "string" && (FIELDS as readonly string[]).includes(field as FieldPath<FormValues>)) {
      setError(field as Field, { type: "server", message: t(FIELD_MESSAGE[field as Field]) }, { shouldFocus: !mapped });
      mapped = true;
    }
  }
  return mapped;
}
