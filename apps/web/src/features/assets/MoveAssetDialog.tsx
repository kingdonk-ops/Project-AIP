/**
 * Move an asset under another parent, or to the top level (ASSETS-03): `POST /assets/{id}/move`
 * with the asset's `syncVersion`. The moving asset and its subtree are not offered as parents; the
 * server's answers (422 `PATH_CYCLE`, `ASSET_TREE_TOO_DEEP`, `PARENT_NOT_FOUND`, 409
 * `VERSION_CONFLICT`) are shown in the dialog. On success every asset list (the tree's levels and
 * the register) reloads, so the old and the new parent show the change.
 */
import { useAssetsMove, type AssetOut } from "@aip/api-client";
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle, FormField } from "@aip/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { t } from "../shell/t";
import { invalidateAssets } from "./data";
import { ParentPicker } from "./ParentPicker";
import { errorCode, errorMessage, withReference } from "./terms";

export interface MoveAssetDialogProps {
  asset: Pick<AssetOut, "id" | "name" | "parentId" | "syncVersion">;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onMoved: (asset: AssetOut) => void;
}

export function MoveAssetDialog({ asset, open, onOpenChange, onMoved }: MoveAssetDialogProps) {
  const [parentId, setParentId] = useState(asset.parentId ?? "");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const move = useAssetsMove();

  const submit = async () => {
    setError(null);
    const response = await move.mutateAsync({
      assetId: asset.id,
      data: { syncVersion: asset.syncVersion, parentId: parentId || null },
    });
    if (response.status === 200) {
      await invalidateAssets(queryClient, asset.id);
      onMoved(response.data);
      onOpenChange(false);
      return;
    }
    setError(withReference(errorMessage(errorCode(response.data as unknown)), response.headers));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("assets.move.close")}>
        <DialogTitle>{t("assets.move.title", { name: asset.name })}</DialogTitle>
        <DialogDescription>{t("assets.move.description")}</DialogDescription>
        <form
          noValidate
          className="assets-move"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <FormField label={t("assets.move.parent")}>
            {(control) => (
              <ParentPicker
                id={control.id}
                label={t("assets.move.parent")}
                value={parentId}
                onChange={setParentId}
                topLevelLabel={t("assets.move.top_level")}
                exclude={asset.id}
                placeholder={t("assets.form.parent_search")}
              />
            )}
          </FormField>
          {error ? (
            <p role="alert" className="aip-form-field__error">
              {error}
            </p>
          ) : null}
          <div className="assets-form__actions">
            <Button type="submit" disabled={move.isPending}>
              {move.isPending ? t("assets.move.moving") : t("assets.move.submit")}
            </Button>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              {t("assets.move.cancel")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
