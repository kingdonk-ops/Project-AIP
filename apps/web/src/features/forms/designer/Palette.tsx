/**
 * The designer's palette (FORMS-11): "Section" and the 12 form field types of the shared registry
 * (`@aip/contracts/field-types`), labelled `item_types.field_type.*`. Clicking (or Enter) adds the
 * item; dragging one onto the canvas drops it there. Only the pointer starts a palette drag, so
 * Enter and Space keep meaning "add".
 */
import type { FieldType } from "@aip/form-renderer";
import { useDraggable } from "@dnd-kit/core";
import type { PointerEventHandler } from "react";
import { Button } from "@aip/ui";
import { t } from "../../shell/t";
import { FORM_FIELD_TYPES } from "./model";

export const PALETTE_SECTION = "section";
export const paletteId = (item: FieldType | typeof PALETTE_SECTION) => `palette:${item}`;

function PaletteItem({ item, label, onAdd }: { item: FieldType | typeof PALETTE_SECTION; label: string; onAdd: () => void }) {
  const draggable = useDraggable({ id: paletteId(item), data: { kind: "palette", item } });
  return (
    <li>
      <Button
        ref={draggable.setNodeRef}
        type="button"
        variant="secondary"
        className="dsg-palette__item"
        data-palette={item}
        onPointerDown={draggable.listeners?.onPointerDown as PointerEventHandler<HTMLButtonElement> | undefined}
        onClick={onAdd}
      >
        {label}
      </Button>
    </li>
  );
}

export interface PaletteProps {
  onAddSection: () => void;
  onAddField: (type: FieldType) => void;
}

export function Palette({ onAddSection, onAddField }: PaletteProps) {
  return (
    <div className="dsg-palette" data-testid="designer-palette">
      <p className="dsg-palette__hint">{t("forms.designer.palette.hint")}</p>
      <ul className="dsg-palette__list">
        <PaletteItem item={PALETTE_SECTION} label={t("forms.designer.palette.section")} onAdd={onAddSection} />
        {FORM_FIELD_TYPES.map((type) => (
          <PaletteItem key={type} item={type} label={t(`item_types.field_type.${type}`)} onAdd={() => onAddField(type)} />
        ))}
      </ul>
    </div>
  );
}
