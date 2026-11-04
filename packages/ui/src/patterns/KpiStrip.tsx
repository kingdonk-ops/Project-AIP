/**
 * KPI strip (DESIGN-09 part B, was DESIGN-11): up to four compact metric tiles. A tile with
 * `onSelect` is a toggle button (`aria-pressed`) that filters the queue below it. A tile the user may
 * not see shows the "restricted" term, never a blank or a zero. The danger tone colours the number
 * and icon, never the tile.
 */
import { Icon, type IconName } from "../components/icon";
import { cn } from "../lib/cn";
import type { Translate } from "../register/types";
import type { StatusTone } from "../tokens/tokens";

export const KPI_MAX_TILES = 4;

export interface KpiTile {
  id: string;
  labelKey: string;
  value?: number | string;
  tone?: StatusTone;
  icon: IconName;
  /** Term key of a short hint under the value. */
  hintKey?: string;
  /** Makes the tile a toggle; `pressed` is its state. */
  onSelect?: () => void;
  pressed?: boolean;
  /** The user may not see this metric: show the restricted state instead of a number. */
  restricted?: boolean;
}

export interface KpiStripProps {
  tiles: readonly KpiTile[];
  /** Term key naming the strip (a list). */
  labelKey: string;
  translate: Translate;
}

function TileBody({ tile, translate }: { tile: KpiTile; translate: Translate }) {
  const tone = tile.restricted ? "neutral" : (tile.tone ?? "neutral");
  return (
    <>
      <span className="aip-kpi__label">{translate(tile.labelKey)}</span>
      <span className={cn("aip-kpi__value", `aip-kpi__value--${tone}`)}>
        <Icon name={tile.restricted ? "shield" : tile.icon} size={16} />
        {tile.restricted ? (
          <span className="aip-kpi__restricted">{translate("ui.kpi.restricted")}</span>
        ) : (
          <span className="aip-kpi__number">{tile.value}</span>
        )}
      </span>
      {tile.hintKey && !tile.restricted && <span className="aip-kpi__hint">{translate(tile.hintKey)}</span>}
    </>
  );
}

export function KpiStrip({ tiles, labelKey, translate }: KpiStripProps) {
  return (
    <ul className="aip-kpi" aria-label={translate(labelKey)}>
      {tiles.slice(0, KPI_MAX_TILES).map((tile) => (
        <li key={tile.id} className="aip-kpi__item">
          {tile.onSelect && !tile.restricted ? (
            <button
              type="button"
              className="aip-kpi__tile aip-kpi__tile--toggle"
              aria-pressed={tile.pressed ?? false}
              onClick={tile.onSelect}
            >
              <TileBody tile={tile} translate={translate} />
            </button>
          ) : (
            <div className="aip-kpi__tile" data-restricted={tile.restricted ? "true" : undefined}>
              <TileBody tile={tile} translate={translate} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
