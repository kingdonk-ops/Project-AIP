/**
 * Create or edit a site (PROJECTS-07) in a dialog. The body is validated by the Zod schema orval
 * generates from the API's OpenAPI document (`schemas.SitesCreateBody` / `SitesUpdateBody`), so the
 * Pydantic models in PROJECTS-01 stay the source of truth; the server's answers (409 code taken,
 * 422 field errors) land on their inputs. `site` is undefined for create, set for edit.
 */
import {
  getSitesListQueryKey,
  schemas,
  useSitesCreate,
  useSitesUpdate,
  type SiteCreate,
  type SiteOut,
  type SiteUpdate,
} from "@aip/api-client";
import { Button, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, FormField, Input, toast } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, type UseFormSetError } from "react-hook-form";
import { t } from "../shell/t";

type Field = "code" | "name" | "timezone" | "lat" | "lng";
const FIELDS: readonly Field[] = ["code", "name", "timezone", "lat", "lng"];
const FIELD_MESSAGE: Record<Field, string> = {
  code: "sites.error.code",
  name: "sites.error.name",
  timezone: "sites.error.timezone",
  lat: "sites.error.lat",
  lng: "sites.error.lng",
};
const DOMAIN_ERRORS: Record<string, [Field, string]> = {
  SITE_CODE_TAKEN: ["code", "sites.error.code_taken"],
};

interface FormValues {
  code: string;
  name: string;
  timezone: string;
  lat: string;
  lng: string;
}

function initialValues(site?: SiteOut): FormValues {
  return {
    code: site?.code ?? "",
    name: site?.name ?? "",
    timezone: site?.timezone ?? "",
    lat: site?.lat ?? "",
    lng: site?.lng ?? "",
  };
}

export interface SiteFormDialogProps {
  open: boolean;
  /** Undefined creates a site; a site edits it. */
  site?: SiteOut | undefined;
  onOpenChange: (open: boolean) => void;
}

export function SiteFormDialog({ open, site, onOpenChange }: SiteFormDialogProps) {
  const editing = site !== undefined;
  const [formError, setFormError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const create = useSitesCreate();
  const update = useSitesUpdate();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ values: initialValues(site) });

  const errorOf = (field: Field): { error?: string } => {
    const error = errors[field];
    if (!error) return {};
    return { error: error.type === "server" && error.message ? error.message : t(FIELD_MESSAGE[field]) };
  };

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    const orNull = (value: string) => (value.trim() === "" ? null : value.trim());
    const base = { code: values.code.trim(), name: values.name.trim(), timezone: orNull(values.timezone), lat: orNull(values.lat), lng: orNull(values.lng) };
    const schema = editing ? schemas.SitesUpdateBody : schemas.SitesCreateBody;
    const parsed = schema.safeParse(base);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        const field = issue.path[0];
        if (typeof field === "string" && (FIELDS as readonly string[]).includes(field)) {
          setError(field as Field, { type: "client", message: t(FIELD_MESSAGE[field as Field]) }, { shouldFocus: true });
        }
      }
      return;
    }

    const response = editing
      ? await update.mutateAsync({ siteId: site.id, data: base as SiteUpdate })
      : await create.mutateAsync({ data: base as SiteCreate });

    if (response.status === 200 || response.status === 201) {
      await queryClient.invalidateQueries({ queryKey: getSitesListQueryKey().slice(0, 1) });
      toast.success(editing ? "sites.form.saved" : "sites.form.created", { code: response.data.code });
      onOpenChange(false);
      return;
    }
    if (!applySiteServerErrors(response.data as unknown, setError)) {
      const id = response.headers.get("x-request-id");
      setFormError(id ? `${t("sites.error.save")} ${t("sites.error.request_id", { id })}` : t("sites.error.save"));
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("ui.close")}>
        <DialogTitle>{t(editing ? "sites.edit.title" : "sites.create.title")}</DialogTitle>
        <DialogDescription>{t("sites.register.caption")}</DialogDescription>
        <form className="sites-form" noValidate onSubmit={(e) => void onSubmit(e)}>
          <FormField label={t("sites.field.code")} hint={t("sites.field.code_hint")} {...errorOf("code")}>
            {(control) => <Input {...control} autoComplete="off" className="projects-register__mono" {...register("code")} />}
          </FormField>
          <FormField label={t("sites.field.name")} {...errorOf("name")}>
            {(control) => <Input {...control} {...register("name")} />}
          </FormField>
          <FormField label={t("sites.field.timezone")} hint={t("sites.field.timezone_hint")} {...errorOf("timezone")}>
            {(control) => <Input {...control} {...register("timezone")} />}
          </FormField>
          <FormField label={t("sites.field.lat")} hint={t("sites.field.lat_hint")} {...errorOf("lat")}>
            {(control) => <Input {...control} inputMode="decimal" {...register("lat")} />}
          </FormField>
          <FormField label={t("sites.field.lng")} hint={t("sites.field.lng_hint")} {...errorOf("lng")}>
            {(control) => <Input {...control} inputMode="decimal" {...register("lng")} />}
          </FormField>
          {formError ? (
            <p role="alert" className="aip-form-field__error">
              {formError}
            </p>
          ) : null}
          <div className="projects-form__actions">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? t("sites.form.saving") : t("sites.form.submit")}
            </Button>
            <DialogClose asChild>
              <Button type="button" variant="ghost">
                {t("sites.form.cancel")}
              </Button>
            </DialogClose>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type SetError = UseFormSetError<FormValues>;

/** Put a 409/422 body's errors on their inputs. Returns false when nothing could be mapped. */
export function applySiteServerErrors(body: unknown, setError: SetError): boolean {
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
    if (typeof field === "string" && (FIELDS as readonly string[]).includes(field)) {
      setError(field as Field, { type: "server", message: t(FIELD_MESSAGE[field as Field]) }, { shouldFocus: !mapped });
      mapped = true;
    }
  }
  return mapped;
}
