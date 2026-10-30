/**
 * Column definitions of the assets register (ASSETS-03). Name, Tag Number and Updated sort both ways
 * on the server. Item type and Parent are looked up for the page's rows (see `AssetsRegister`).
 * Row actions are shown only with their permission; the server refuses them regardless.
 */
import type { AssetOut } from "@aip/api-client";
import { Button, type RegisterColumn } from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { t } from "../shell/t";

/** A register row: the asset plus the names looked up for it. */
export type AssetRow = AssetOut & {
  /** The parent's breadcrumb (`Site A > Unit 1`), empty for a top-level asset. */
  parentCrumb: string;
  itemTypeName: string;
};

export interface AssetColumnContext {
  permissions: readonly string[];
  onMove: (asset: AssetRow) => void;
}

// ADR 0025: instants are shown in the viewer's own time zone.
const updatedFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function RowActions({ asset, permissions, onMove }: { asset: AssetRow } & AssetColumnContext) {
  const can = (permission: string) => permissions.includes(permission);
  return (
    <div className="assets-register__actions">
      {can("asset.update") ? (
        <Button variant="ghost" asChild>
          <Link to="/assets/$assetId/edit" params={{ assetId: asset.id }} aria-label={t("assets.register.edit_named", { name: asset.name })}>
            {t("assets.register.edit")}
          </Link>
        </Button>
      ) : null}
      {can("asset.create") ? (
        <Button variant="ghost" asChild>
          <Link
            to="/assets/new"
            search={{ parentId: asset.id }}
            aria-label={t("assets.register.add_child_named", { name: asset.name })}
          >
            {t("assets.register.add_child")}
          </Link>
        </Button>
      ) : null}
      {can("asset.move") ? (
        <Button variant="ghost" aria-label={t("assets.register.move_named", { name: asset.name })} onClick={() => onMove(asset)}>
          {t("assets.register.move")}
        </Button>
      ) : null}
    </div>
  );
}

export function assetColumns(context: AssetColumnContext): RegisterColumn<AssetRow>[] {
  return [
    {
      id: "name",
      headerKey: "assets.field.name",
      cell: (a) => (
        <Link to="/assets/$assetId/edit" params={{ assetId: a.id }} className="assets-register__name">
          {a.name}
        </Link>
      ),
      csv: (a) => a.name,
      sortable: true,
    },
    { id: "tagNumber", headerKey: "assets.field.tag_number", cell: (a) => a.tagNumber ?? "", mono: true, sortable: true },
    { id: "internalTag", headerKey: "assets.field.internal_tag", cell: (a) => a.internalTag, mono: true },
    { id: "itemType", headerKey: "assets.field.item_type", cell: (a) => a.itemTypeName },
    { id: "parent", headerKey: "assets.field.parent", cell: (a) => a.parentCrumb },
    {
      id: "updated",
      headerKey: "assets.field.updated",
      cell: (a) => <time dateTime={a.updatedAt}>{updatedFormat.format(new Date(a.updatedAt))}</time>,
      csv: (a) => a.updatedAt,
      sortable: true,
    },
    {
      id: "actions",
      headerKey: "assets.field.actions",
      cell: (a) => <RowActions asset={a} {...context} />,
      csv: () => "",
    },
  ];
}
