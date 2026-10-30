/**
 * The form template register (FORMS-04) on DESIGN-03's `RegisterTable`: kind and status as quick
 * filters, search on code or name, all in the URL (see `search.ts`). FORMS-01's list returns up to
 * 200 templates in code order with no cursor, so there is one page and no sortable column (FORMS-09).
 * With `form.manage` the page offers "Upload template"; the server checks the permission again.
 */
import { useFormsTemplatesList, type TemplateListItem } from "@aip/api-client";
import {
  Button,
  RegisterTable,
  type RegisterFilter,
  type RegisterQuery,
  type RegisterQueryResult,
  type Translate,
} from "@aip/ui";
import { useMemo, useState } from "react";
import { t } from "../shell/t";
import { templateColumns } from "./columns";
import { PAGE_SIZES, TEMPLATE_STATUSES, toListParams } from "./search";
import { TEMPLATE_KINDS } from "./templateJson";
import { TemplateUploadDialog } from "./TemplateUploadDialog";

/** The register's generic labels, worded for templates. */
const TERMS: Readonly<Record<string, string>> = {
  "register.search": "forms.templates.register.search",
  "register.any": "forms.templates.register.any",
  "register.clearAll": "forms.templates.register.clear",
  "register.empty": "forms.templates.register.empty_filtered",
  "register.loading": "forms.templates.register.loading",
  "register.error": "forms.templates.register.error",
  "register.reference": "forms.templates.register.request_id",
  "register.retry": "forms.templates.register.retry",
  "register.previous": "forms.templates.register.previous",
  "register.next": "forms.templates.register.next",
  "register.pagination": "forms.templates.register.page_label",
};

const translate: Translate = (key, params) => t(TERMS[key] ?? key, params);

const filters: readonly RegisterFilter[] = [
  {
    id: "kind",
    kind: "select",
    labelKey: "forms.templates.field.kind",
    quick: true,
    options: TEMPLATE_KINDS.map((value) => ({ value, labelKey: `forms.kind.${value}` })),
  },
  {
    id: "status",
    kind: "select",
    labelKey: "forms.templates.field.status",
    quick: true,
    options: TEMPLATE_STATUSES.map((value) => ({ value, labelKey: `forms.template.status.${value}` })),
  },
];

function useTemplatesPage(query: RegisterQuery): RegisterQueryResult<TemplateListItem> {
  const list = useFormsTemplatesList(toListParams(query));
  const response = list.data;
  const failed = response !== undefined && response.status !== 200;
  return {
    data: response?.status === 200 ? { items: response.data.items, nextCursor: null } : undefined,
    isPending: list.isPending,
    isError: list.isError || failed,
    refetch: () => void list.refetch(),
    requestId: failed ? response.headers.get("x-request-id") : null,
  };
}

export interface TemplatesRegisterProps {
  query: RegisterQuery;
  permissions: readonly string[];
  onQueryChange: (next: RegisterQuery) => void;
  onOpenTemplate: (templateId: string) => void;
}

export function TemplatesRegister({ query, permissions, onQueryChange, onOpenTemplate }: TemplatesRegisterProps) {
  const canManage = permissions.includes("form.manage");
  const [uploading, setUploading] = useState(false);
  const columns = useMemo(() => templateColumns(), []);
  const filtered = Object.keys(query.filters).length > 0 || Boolean(query.q);

  return (
    <section className="forms-register" aria-labelledby="form-templates-title">
      <div className="forms-register__header">
        <h1 id="form-templates-title">{t("forms.templates.register.title")}</h1>
        {canManage ? <Button onClick={() => setUploading(true)}>{t("forms.templates.register.upload")}</Button> : null}
      </div>

      <RegisterTable<TemplateListItem>
        id="form-templates"
        captionKey="forms.templates.register.caption"
        columns={columns}
        filters={filters}
        query={query}
        onQueryChange={onQueryChange}
        useQuery={useTemplatesPage}
        rowId={(row) => row.id}
        onOpenRow={(row) => onOpenTemplate(row.id)}
        permissions={permissions}
        pageSizes={PAGE_SIZES}
        translate={translate}
        empty={
          filtered ? undefined : (
            <div className="forms-register__empty">
              <p>{t("forms.templates.register.empty")}</p>
              {canManage ? (
                <Button variant="secondary" onClick={() => setUploading(true)}>
                  {t("forms.templates.register.upload")}
                </Button>
              ) : null}
            </div>
          )
        }
      />

      {canManage ? (
        <TemplateUploadDialog open={uploading} onOpenChange={setUploading} onCreated={onOpenTemplate} />
      ) : null}
    </section>
  );
}
