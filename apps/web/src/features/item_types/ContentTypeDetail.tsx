/**
 * Content type detail `/admin/content-types/$contentTypeId` (ITEMTYPES-03) on DESIGN-04's
 * `RecordDetail`, with tabs in the URL (`?tab=details|categories|item-types`):
 *
 * - Details: the definition form (name, icon, show in navigation; the key is fixed), saved with
 *   `syncVersion`; a 409 `VERSION_CONFLICT` shows DESIGN-04's "changed by someone else" state.
 * - Categories: name, key, applicable for and item-type count, with Add / Edit / Delete.
 * - Item types: name, key, category, published version and whether a draft exists, with Add; a
 *   row's name opens the item-type editor.
 *
 * Another tenant's id or a missing one is a 404 from the API (RLS) and renders `ErrorState`.
 * Edit controls need `item_type.manage` (the definition) or `item_type.edit` (categories and item
 * types); the server checks every call.
 */
import type { CategoryOut, ContentTypeOut, ItemTypeOut } from "@aip/api-client";
import {
  Button,
  confirm,
  ErrorState,
  FormField,
  iconNames,
  Input,
  LoadingState,
  RecordDetail,
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  toast,
  type RecordTab,
  type RequestError,
} from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { useMemo, useState, type FormEvent } from "react";
import { t } from "../shell/t";
import { errorCode, requestId, useCategories, useContentType, useDeleteCategory, useItemTypes, useUpdateContentType } from "./api";
import { CategoryDialog } from "./CategoryDialog";
import { CheckField } from "./ContentTypeDialog";
import { ItemTypeDialog } from "./ItemTypeDialog";

export const CONTENT_TYPE_TABS = ["details", "categories", "item-types"] as const;
export type ContentTypeTab = (typeof CONTENT_TYPE_TABS)[number];

export function validateContentTypeSearch(search: Record<string, unknown>): { tab?: ContentTypeTab } {
  const tab = search.tab;
  return typeof tab === "string" && (CONTENT_TYPE_TABS as readonly string[]).includes(tab) ? { tab: tab as ContentTypeTab } : {};
}

export interface ContentTypeDetailProps {
  contentTypeId: string;
  permissions: readonly string[];
  tab: ContentTypeTab | undefined;
  onTabChange: (tab: ContentTypeTab) => void;
}

export function ContentTypeDetail({ contentTypeId, permissions, tab, onTabChange }: ContentTypeDetailProps) {
  const query = useContentType(contentTypeId);
  const response = query.data;
  if (query.isPending || (query.isError && query.isFetching)) {
    return (
      <main className="item-types-page" aria-busy="true">
        <LoadingState variant="spinner" translate={t} />
      </main>
    );
  }
  if (query.isError || response === undefined || response.status !== 200) {
    const error: RequestError = response ? { status: response.status, requestId: requestId(response) } : {};
    return (
      <main className="item-types-page">
        <ErrorState error={error} onRetry={() => void query.refetch()} translate={t} />
      </main>
    );
  }
  const contentType = response.data;

  const tabs: RecordTab[] = [
    {
      id: "details",
      content: (
        <ContentTypeForm
          key={contentType.syncVersion}
          contentType={contentType}
          canManage={permissions.includes("item_type.manage")}
          onReload={() => void query.refetch()}
        />
      ),
    },
    {
      id: "categories",
      labelKey: "item_types.tab.categories",
      content: <CategoriesTab contentTypeId={contentType.id} canEdit={permissions.includes("item_type.edit")} />,
    },
    {
      id: "item-types",
      labelKey: "item_types.tab.item_types",
      content: <ItemTypesTab contentTypeId={contentType.id} canEdit={permissions.includes("item_type.edit")} />,
    },
  ];

  return (
    <main className="item-types-page">
      <RecordDetail
        id={contentType.key}
        title={contentType.name}
        breadcrumb={
          <nav aria-label={t("item_types.breadcrumb")}>
            <Link to="/admin/content-types">{t("item_types.register.title")}</Link>
          </nav>
        }
        status={
          contentType.showInNav
            ? { tone: "info", icon: "check", labelKey: "item_types.content_type.status.in_nav" }
            : { tone: "neutral", icon: "minus", labelKey: "item_types.content_type.status.hidden" }
        }
        tabs={tabs}
        tab={tab ?? "details"}
        onTabChange={(next) => onTabChange(next as ContentTypeTab)}
        railKey="content-type"
        translate={t}
      />
    </main>
  );
}

function Facts({ rows }: { rows: readonly [string, string, boolean?][] }) {
  return (
    <dl className="item-types-facts">
      {rows.map(([key, value, mono]) => (
        <div key={key} className="item-types-facts__row">
          <dt>{t(key)}</dt>
          <dd className={mono ? "item-types-mono" : undefined}>{value || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

function ContentTypeForm({ contentType, canManage, onReload }: { contentType: ContentTypeOut; canManage: boolean; onReload: () => void }) {
  const update = useUpdateContentType();
  const [name, setName] = useState(contentType.name);
  const [icon, setIcon] = useState(contentType.icon);
  const [showInNav, setShowInNav] = useState(contentType.showInNav);
  const [nameError, setNameError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  if (!canManage) {
    return (
      <section aria-labelledby="content-type-facts">
        <h2 id="content-type-facts">{t("item_types.content_type.details")}</h2>
        <Facts
          rows={[
            ["item_types.content_type.field.key", contentType.key, true],
            ["item_types.content_type.field.name", contentType.name],
            ["item_types.content_type.field.icon", contentType.icon, true],
            ["item_types.content_type.field.show_in_nav", t(contentType.showInNav ? "item_types.yes" : "item_types.no")],
          ]}
        />
      </section>
    );
  }
  if (conflict) {
    return <ErrorState error={{ status: 409 }} onRetry={onReload} translate={t} />;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (!name.trim()) {
      setNameError(t("item_types.error.name"));
      return;
    }
    setNameError(null);
    const response = await update.mutateAsync({
      contentTypeId: contentType.id,
      data: { syncVersion: contentType.syncVersion, name: name.trim(), icon, showInNav },
    });
    if (response.status === 200) {
      toast.success("item_types.content_type.saved", { name: response.data.name });
      return;
    }
    if (errorCode(response.data) === "VERSION_CONFLICT") {
      setConflict(true);
      return;
    }
    const id = requestId(response);
    setFormError(id ? `${t("item_types.error.save")} ${t("item_types.error.request_id", { id })}` : t("item_types.error.save"));
  }

  return (
    <form className="item-types-form" noValidate aria-labelledby="content-type-form-title" onSubmit={(e) => void submit(e)}>
      <h2 id="content-type-form-title">{t("item_types.content_type.details")}</h2>
      <FormField label={t("item_types.content_type.field.key")} hint={t("item_types.field.key_fixed")}>
        {(control) => <Input {...control} className="item-types-mono" value={contentType.key} readOnly />}
      </FormField>
      <FormField label={t("item_types.content_type.field.name")} {...(nameError ? { error: nameError } : {})}>
        {(control) => <Input {...control} value={name} onChange={(e) => setName(e.target.value)} />}
      </FormField>
      <FormField label={t("item_types.content_type.field.icon")}>
        {(control) => (
          <select {...control} className="item-types-select" value={icon} onChange={(e) => setIcon(e.target.value)}>
            {iconNames.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        )}
      </FormField>
      <CheckField checked={showInNav} onChange={setShowInNav} label={t("item_types.content_type.field.show_in_nav")} />
      {formError ? (
        <p role="alert" className="aip-form-field__error">
          {formError}
        </p>
      ) : null}
      <div className="item-types-form__actions">
        <Button type="submit" disabled={update.isPending}>
          {t("item_types.action.save")}
        </Button>
      </div>
    </form>
  );
}

function CategoriesTab({ contentTypeId, canEdit }: { contentTypeId: string; canEdit: boolean }) {
  const categories = useCategories(contentTypeId);
  const itemTypes = useItemTypes(contentTypeId);
  const remove = useDeleteCategory();
  const [dialog, setDialog] = useState<{ category?: CategoryOut } | null>(null);
  const items = categories.data?.status === 200 ? categories.data.data.items : [];
  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const it of itemTypes.data?.status === 200 ? itemTypes.data.data.items : []) {
      map.set(it.categoryId, (map.get(it.categoryId) ?? 0) + 1);
    }
    return map;
  }, [itemTypes.data]);

  async function del(category: CategoryOut) {
    const ok = await confirm({
      titleKey: "item_types.category.delete.title",
      bodyKey: "item_types.category.delete.body",
      confirmKey: "item_types.category.delete.submit",
      params: { name: category.name },
      tone: "danger",
    });
    if (!ok) return;
    const response = await remove.mutateAsync({ categoryId: category.id });
    if (response.status === 204) {
      toast.success("item_types.category.deleted", { name: category.name });
      return;
    }
    const data = response.data as Record<string, unknown>;
    if (errorCode(data) === "CATEGORY_IN_USE") {
      toast.error("item_types.category.delete.in_use", { count: Number(data.itemTypes ?? 0) });
    } else toast.error("item_types.error.save");
  }

  if (categories.isPending) return <LoadingState variant="skeleton" translate={t} />;
  if (categories.data?.status !== 200) {
    return <ErrorState error={categories.data ? { status: categories.data.status } : {}} onRetry={() => void categories.refetch()} translate={t} />;
  }

  return (
    <section aria-labelledby="categories-title" className="item-types-tab">
      <div className="item-types-page__header">
        <h2 id="categories-title">{t("item_types.tab.categories")}</h2>
        {canEdit ? <Button onClick={() => setDialog({})}>{t("item_types.category.add")}</Button> : null}
      </div>
      {items.length === 0 ? (
        <p>{t("item_types.empty.categories")}</p>
      ) : (
        <div className="item-types-table">
          <Table>
            <TableCaption>{t("item_types.category.caption")}</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>{t("item_types.category.field.name")}</TableHead>
                <TableHead>{t("item_types.category.field.key")}</TableHead>
                <TableHead>{t("item_types.category.field.applicable_for")}</TableHead>
                <TableHead>{t("item_types.content_type.field.item_types")}</TableHead>
                {canEdit ? <TableHead>{t("item_types.column.actions")}</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>{c.name}</TableCell>
                  <TableCell className="item-types-mono">{c.key}</TableCell>
                  <TableCell>{t(`item_types.applicable_for.${c.applicableFor}`)}</TableCell>
                  <TableCell>{counts.get(c.id) ?? 0}</TableCell>
                  {canEdit ? (
                    <TableCell>
                      <span className="item-types-actions">
                        <Button variant="ghost" aria-label={t("item_types.category.edit_named", { name: c.name })} onClick={() => setDialog({ category: c })}>
                          {t("item_types.action.edit")}
                        </Button>
                        <Button
                          variant="ghost"
                          disabled={remove.isPending}
                          aria-label={t("item_types.category.delete_named", { name: c.name })}
                          onClick={() => void del(c)}
                        >
                          {t("item_types.action.delete")}
                        </Button>
                      </span>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {canEdit ? (
        <CategoryDialog
          open={dialog !== null}
          contentTypeId={contentTypeId}
          category={dialog?.category}
          onOpenChange={(open) => {
            if (!open) setDialog(null);
          }}
        />
      ) : null}
    </section>
  );
}

function ItemTypesTab({ contentTypeId, canEdit }: { contentTypeId: string; canEdit: boolean }) {
  const itemTypes = useItemTypes(contentTypeId);
  const categories = useCategories(contentTypeId);
  const [adding, setAdding] = useState(false);
  const categoryList = categories.data?.status === 200 ? categories.data.data.items : [];
  const categoryNames = new Map(categoryList.map((c) => [c.id, c.name]));

  if (itemTypes.isPending) return <LoadingState variant="skeleton" translate={t} />;
  if (itemTypes.data?.status !== 200) {
    return <ErrorState error={itemTypes.data ? { status: itemTypes.data.status } : {}} onRetry={() => void itemTypes.refetch()} translate={t} />;
  }
  const items: readonly ItemTypeOut[] = itemTypes.data.data.items;

  return (
    <section aria-labelledby="item-types-title" className="item-types-tab">
      <div className="item-types-page__header">
        <h2 id="item-types-title">{t("item_types.tab.item_types")}</h2>
        {canEdit ? (
          <Button disabled={categoryList.length === 0} onClick={() => setAdding(true)}>
            {t("item_types.item_type.add")}
          </Button>
        ) : null}
      </div>
      {canEdit && categoryList.length === 0 ? <p>{t("item_types.item_type.needs_category")}</p> : null}
      {items.length === 0 ? (
        <p>{t("item_types.empty.item_types")}</p>
      ) : (
        <div className="item-types-table">
          <Table>
            <TableCaption>{t("item_types.item_type.caption")}</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>{t("item_types.item_type.field.name")}</TableHead>
                <TableHead>{t("item_types.item_type.field.key")}</TableHead>
                <TableHead>{t("item_types.item_type.field.category")}</TableHead>
                <TableHead>{t("item_types.item_type.field.published")}</TableHead>
                <TableHead>{t("item_types.item_type.field.draft")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((it) => (
                <TableRow key={it.id}>
                  <TableCell>
                    <Link
                      to="/admin/content-types/$contentTypeId/item-types/$itemTypeId"
                      params={{ contentTypeId, itemTypeId: it.id }}
                    >
                      {it.name}
                    </Link>
                  </TableCell>
                  <TableCell className="item-types-mono">{it.key}</TableCell>
                  <TableCell>{categoryNames.get(it.categoryId) ?? ""}</TableCell>
                  <TableCell>
                    {it.publishedVersion ? t("item_types.status.published", { version: it.publishedVersion }) : t("item_types.status.not_published")}
                  </TableCell>
                  <TableCell>{t(it.draftVersionId ? "item_types.yes" : "item_types.no")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {canEdit ? <ItemTypeDialog open={adding} categories={categoryList} onOpenChange={setAdding} /> : null}
    </section>
  );
}
