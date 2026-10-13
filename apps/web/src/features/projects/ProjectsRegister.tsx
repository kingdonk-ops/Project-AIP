/**
 * The projects register (PROJECTS-02): server-side cursor pagination, status filter and search,
 * all held in the URL by the route. Uses the `packages/ui` table primitives through the column
 * definitions in `columns.tsx`; DESIGN-03's `RegisterTable` replaces the table markup later.
 */
import { useProjectsList, useSitesList } from "@aip/api-client";
import {
  Button,
  Icon,
  Input,
  Label,
  Spinner,
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { t } from "../shell/t";
import { projectColumns } from "./columns";
import { DEFAULT_LIMIT, PROJECT_STATUSES, type ProjectsSearch } from "./search";

const SEARCH_DEBOUNCE_MS = 300;
const SITE_LOOKUP_LIMIT = 200;

/** A change to the search; `undefined` removes a key. */
type SearchPatch = { [K in keyof ProjectsSearch]?: ProjectsSearch[K] | undefined };

export interface ProjectsRegisterProps {
  search: ProjectsSearch;
  permissions: readonly string[];
  /** Replace the URL search (the route navigates with `replace: true`). */
  onSearchChange: (next: ProjectsSearch) => void;
}

export function ProjectsRegister({ search, permissions, onSearchChange }: ProjectsRegisterProps) {
  const canCreate = permissions.includes("project.create");
  const limit = search.limit ?? DEFAULT_LIMIT;
  const list = useProjectsList({
    limit,
    ...(search.cursor ? { cursor: search.cursor } : {}),
    ...(search.status ? { status: [search.status] } : {}),
    ...(search.q ? { q: search.q } : {}),
  });
  const sites = useSitesList({ limit: SITE_LOOKUP_LIMIT });
  const siteNames = useMemo(() => {
    const items = sites.data?.status === 200 ? sites.data.data.items : [];
    return new Map(items.map((s) => [s.id, s.name]));
  }, [sites.data]);
  const columns = useMemo(() => projectColumns({ siteNames }), [siteNames]);

  // The API pages forward only; earlier cursors are remembered here for Previous. A reload keeps
  // the current page (its cursor is in the URL) and Previous then returns to the first page.
  const [previous, setPrevious] = useState<(string | undefined)[]>([]);

  /** Apply a change; any change except a page move starts again from the first page. */
  const changeFilters = (patch: SearchPatch) => {
    if (!("cursor" in patch)) setPrevious([]);
    const rest: SearchPatch = { ...search };
    delete rest.cursor;
    delete rest.created;
    const merged: SearchPatch = { ...rest, ...patch };
    const next = Object.fromEntries(Object.entries(merged).filter(([, v]) => v !== undefined)) as ProjectsSearch;
    onSearchChange(next);
  };

  const response = list.data;
  const page = response?.status === 200 ? response.data : undefined;
  const failed = list.isError || (response !== undefined && response.status !== 200);
  const requestId = response && response.status !== 200 ? response.headers.get("x-request-id") : null;
  const filtered = Boolean(search.status || search.q);

  return (
    <section className="projects-register" aria-labelledby="projects-title">
      <div className="projects-register__header">
        <h1 id="projects-title">{t("projects.register.title")}</h1>
        {canCreate ? (
          <Button asChild>
            <Link to="/projects/new">{t("projects.register.create")}</Link>
          </Button>
        ) : null}
      </div>

      {search.created ? (
        <p role="status" className="projects-register__notice">
          {t("projects.register.created", { code: search.created })}
        </p>
      ) : null}

      <FilterBar search={search} onChange={changeFilters} />

      {failed ? (
        <div role="alert" className="projects-register__state">
          <Icon name="alert" />
          <p>{t("projects.error.title")}</p>
          {requestId ? <p className="projects-register__ref">{t("projects.error.request_id", { id: requestId })}</p> : null}
          <Button variant="secondary" onClick={() => void list.refetch()}>
            {t("projects.error.retry")}
          </Button>
        </div>
      ) : list.isPending ? (
        <div className="projects-register__state">
          <Spinner label={t("projects.loading")} />
        </div>
      ) : page && page.items.length === 0 ? (
        <div className="projects-register__state">
          <p>{t(filtered ? "projects.empty.filtered" : "projects.empty.title")}</p>
          {canCreate && !filtered ? (
            <Button asChild>
              <Link to="/projects/new">{t("projects.register.create")}</Link>
            </Button>
          ) : null}
        </div>
      ) : page ? (
        <>
          <div className="projects-register__table">
            <Table>
              <TableCaption className="sr-only">{t("projects.register.caption")}</TableCaption>
              <TableHeader>
                <TableRow>
                  {columns.map((c) => (
                    <TableHead key={c.id}>{t(c.headerKey)}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.items.map((project) => (
                  <TableRow key={project.id}>
                    {columns.map((c) => (
                      <TableCell key={c.id} className={c.mono ? "projects-register__mono" : undefined}>
                        {c.cell(project)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <nav className="projects-register__pages" aria-label={t("projects.page.label")}>
            <Button
              variant="secondary"
              disabled={previous.length === 0 && !search.cursor}
              onClick={() => {
                const stack = [...previous];
                const back = stack.pop();
                setPrevious(stack);
                changeFilters(back ? { cursor: back } : {});
              }}
            >
              {t("projects.page.previous")}
            </Button>
            <Button
              variant="secondary"
              disabled={!page.nextCursor}
              onClick={() => {
                if (!page.nextCursor) return;
                setPrevious([...previous, search.cursor]);
                changeFilters({ cursor: page.nextCursor });
              }}
            >
              {t("projects.page.next")}
            </Button>
          </nav>
        </>
      ) : null}
    </section>
  );
}

function FilterBar({ search, onChange }: { search: ProjectsSearch; onChange: (patch: SearchPatch) => void }) {
  const [q, setQ] = useState(search.q ?? "");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  /** Typing updates the box at once and the URL (and the request) 300 ms after the last key. */
  const typeQuery = (value: string) => {
    setQ(value);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => onChange({ q: value.trim() || undefined }), SEARCH_DEBOUNCE_MS);
  };

  return (
    <form role="search" className="projects-register__filters" aria-label={t("projects.filter.label")} onSubmit={(e) => e.preventDefault()}>
      <div className="projects-register__filter">
        <Label htmlFor="projects-status">{t("projects.filter.status")}</Label>
        <select
          id="projects-status"
          className="projects-register__select"
          value={search.status ?? ""}
          onChange={(e) => {
            const value = e.target.value;
            onChange({ status: (PROJECT_STATUSES as readonly string[]).includes(value) ? (value as ProjectsSearch["status"]) : undefined });
          }}
        >
          <option value="">{t("projects.filter.status_all")}</option>
          {PROJECT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`projects.status.${s}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="projects-register__filter">
        <Label htmlFor="projects-q">{t("projects.filter.search")}</Label>
        <Input id="projects-q" type="search" value={q} maxLength={100} onChange={(e) => typeQuery(e.target.value)} />
      </div>
      {search.status || search.q ? (
        <Button
          variant="ghost"
          type="button"
          onClick={() => {
            clearTimeout(timer.current);
            setQ("");
            onChange({ status: undefined, q: undefined });
          }}
        >
          {t("projects.filter.clear")}
        </Button>
      ) : null}
    </form>
  );
}
