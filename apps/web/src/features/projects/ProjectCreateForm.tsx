/**
 * Create a project (PROJECTS-02). Validated by the Zod schema orval generates from the API's
 * OpenAPI document (`schemas.ProjectsCreateBody`), so the Pydantic model in PROJECTS-01 stays the
 * source of truth; the server's answers (409 code taken, 422 field errors) land on their inputs.
 */
import { getProjectsListQueryKey, schemas, useProjectsCreate, useSitesList, type ProjectCreate } from "@aip/api-client";
import { Button, FormField, Input } from "@aip/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useForm, type FieldPath, type UseFormSetError } from "react-hook-form";
import type { z } from "zod";
import { t } from "../shell/t";

const createSchema = schemas.ProjectsCreateBody;
type FormInput = z.input<typeof createSchema>;
type FormOutput = z.output<typeof createSchema>;
type Field = Extract<FieldPath<FormInput>, "code" | "name" | "siteId" | "region" | "timezone" | "currency">;

const FIELDS: readonly Field[] = ["code", "name", "siteId", "region", "timezone", "currency"];
const SITE_LOOKUP_LIMIT = 200;
// Shown when the client-side schema rejects a field; the server's own codes map in `serverError`.
const FIELD_MESSAGE: Record<Field, string> = {
  code: "projects.error.code",
  name: "projects.error.name",
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

/** The browser's IANA zone when the runtime knows it, else none (the field stays optional). */
export function browserTimeZone(): string | undefined {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const known = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [zone];
    return zone && known.includes(zone) ? zone : undefined;
  } catch {
    return undefined;
  }
}

/** Empty inputs are "not given", not an empty string the schema would reject. */
const optional = (value: unknown) => (value === "" || value === null ? undefined : value);

export interface ProjectCreateFormProps {
  permissions: readonly string[];
  onCreated: (code: string) => void;
}

export function ProjectCreateForm({ permissions, onCreated }: ProjectCreateFormProps) {
  const [denied, setDenied] = useState(!permissions.includes("project.create"));
  const [formError, setFormError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const sites = useSitesList({ limit: SITE_LOOKUP_LIMIT }, { query: { enabled: !denied } });
  const create = useProjectsCreate();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(createSchema),
    defaultValues: { code: "", name: "", currency: "AUD", ...(browserTimeZone() ? { timezone: browserTimeZone() } : {}) },
  });

  if (denied) {
    return (
      <section className="projects-form" aria-labelledby="projects-denied">
        <h1 id="projects-denied">{t("projects.denied.title")}</h1>
        <Link to="/projects">{t("projects.denied.back")}</Link>
      </section>
    );
  }

  // `FormField` takes `error` only when there is one (exactOptionalPropertyTypes).
  const errorOf = (field: Field): { error?: string } => {
    const error = errors[field];
    if (!error) return {};
    return { error: error.type === "server" && error.message ? error.message : t(FIELD_MESSAGE[field]) };
  };

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    // Unset optional fields are left out of the body, not sent as undefined.
    const data = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== undefined)) as unknown as ProjectCreate;
    const response = await create.mutateAsync({ data });
    if (response.status === 201) {
      await queryClient.invalidateQueries({ queryKey: getProjectsListQueryKey().slice(0, 1) });
      onCreated(response.data.code);
      return;
    }
    // 403 is not in the documented responses, but the API answers it without `project.create`.
    if ((response.status as number) === 403) {
      setDenied(true);
      return;
    }
    if (!applyServerErrors(response.data as unknown, setError)) {
      const id = response.headers.get("x-request-id");
      setFormError(id ? `${t("projects.error.save")} ${t("projects.error.request_id", { id })}` : t("projects.error.save"));
    }
  });

  const siteItems = sites.data?.status === 200 ? sites.data.data.items : [];

  return (
    <section className="projects-form" aria-labelledby="projects-create-title">
      <h1 id="projects-create-title">{t("projects.create.title")}</h1>
      <form noValidate onSubmit={(e) => void onSubmit(e)}>
        <FormField label={t("projects.field.code")} hint={t("projects.field.code_hint")} {...errorOf("code")}>
          {(control) => <Input {...control} autoComplete="off" className="projects-register__mono" {...register("code")} />}
        </FormField>
        <FormField label={t("projects.field.name")} {...errorOf("name")}>
          {(control) => <Input {...control} {...register("name")} />}
        </FormField>
        <FormField label={t("projects.field.site")} {...errorOf("siteId")}>
          {(control) => (
            <select {...control} className="projects-register__select" {...register("siteId", { setValueAs: optional })}>
              <option value="">{t("projects.field.site_none")}</option>
              {siteItems.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <FormField label={t("projects.field.region")} hint={t("projects.field.region_hint")} {...errorOf("region")}>
          {(control) => <Input {...control} {...register("region", { setValueAs: optional })} />}
        </FormField>
        <FormField label={t("projects.field.timezone")} hint={t("projects.field.timezone_hint")} {...errorOf("timezone")}>
          {(control) => <Input {...control} {...register("timezone", { setValueAs: optional })} />}
        </FormField>
        <FormField label={t("projects.field.currency")} hint={t("projects.field.currency_hint")} {...errorOf("currency")}>
          {(control) => <Input {...control} maxLength={3} {...register("currency", { setValueAs: optional })} />}
        </FormField>
        {formError ? (
          <p role="alert" className="aip-form-field__error">
            {formError}
          </p>
        ) : null}
        <div className="projects-form__actions">
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? t("projects.create.saving") : t("projects.create.submit")}
          </Button>
          <Button variant="ghost" asChild>
            <Link to="/projects">{t("projects.create.cancel")}</Link>
          </Button>
        </div>
      </form>
    </section>
  );
}

type SetError = UseFormSetError<FormInput>;

/** Put a 409/422 body's errors on their inputs. Returns false when nothing could be mapped. */
export function applyServerErrors(body: unknown, setError: SetError): boolean {
  if (typeof body !== "object" || body === null) return false;
  const record = body as { code?: unknown; field?: unknown; detail?: unknown };
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
    if (typeof field === "string" && (FIELDS as readonly string[]).includes(field)) {
      setError(field as Field, { type: "server", message: t(FIELD_MESSAGE[field as Field]) }, { shouldFocus: !mapped });
      mapped = true;
    }
  }
  return mapped;
}
