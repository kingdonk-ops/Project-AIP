/**
 * The designer's canvas (FORMS-11): sections as panels (label, key in mono, field count) holding
 * field rows (type, label, key in mono, "Required" and "Logic set" chips, lint issue count).
 *
 * Click or Enter selects. Sections and fields reorder by drag (`@dnd-kit/sortable`, keyboard sensor
 * on the handle) and by Alt+ArrowUp / Alt+ArrowDown on the selected row; Delete removes. The
 * `DndContext` is the designer's, so palette items can be dropped here too. Read-only: no handles,
 * no delete, no moves.
 */
import type { FormField, FormSchema, FormSection } from "@aip/form-renderer";
import { useDroppable } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Badge, Button, Panel } from "@aip/ui";
import { useEffect, type KeyboardEvent } from "react";
import { t } from "../../shell/t";
import { FIELD_LOGIC_PROPS, logicSet, SECTION_LOGIC_PROPS, type Selection } from "./model";

export const sectionId = (key: string) => `section:${key}`;
export const fieldId = (key: string) => `field:${key}`;
export const sectionDropId = (key: string) => `drop:${key}`;

export interface FocusRequest {
  key: string;
  /** Changes on every request, so the same key can be focused again. */
  n: number;
}

export interface CanvasProps {
  schema: FormSchema;
  selection: Selection;
  counts: ReadonlyMap<string, number>;
  readOnly: boolean;
  onSelect: (selection: NonNullable<Selection>) => void;
  onMove: (selection: NonNullable<Selection>, delta: -1 | 1) => void;
  onRemove: (selection: NonNullable<Selection>) => void;
  onAddField: (sectionKey: string) => void;
  focus: FocusRequest | null;
}

function rowKeys(
  event: KeyboardEvent<HTMLButtonElement>,
  item: NonNullable<Selection>,
  { onMove, onRemove, readOnly }: Pick<CanvasProps, "onMove" | "onRemove" | "readOnly">,
) {
  if (readOnly) return;
  if (event.altKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
    event.preventDefault();
    onMove(item, event.key === "ArrowUp" ? -1 : 1);
  } else if (event.key === "Delete") {
    event.preventDefault();
    onRemove(item);
  }
}

function IssueCount({ count }: { count: number | undefined }) {
  if (!count) return null;
  return <span className="dsg-chip dsg-chip--issues">{t("forms.designer.canvas.issues", { count })}</span>;
}

function FieldRow({ field, ...props }: CanvasProps & { field: FormField }) {
  const { selection, counts, readOnly, onSelect, onRemove } = props;
  const sortable = useSortable({ id: fieldId(field.key), disabled: readOnly, data: { kind: "field", key: field.key } });
  const selected = selection?.kind === "field" && selection.key === field.key;
  const item = { kind: "field" as const, key: field.key };
  const logic = logicSet(field, FIELD_LOGIC_PROPS).length > 0;
  return (
    <li
      ref={sortable.setNodeRef}
      style={{ transform: CSS.Transform.toString(sortable.transform), transition: sortable.transition }}
      className={selected ? "dsg-row dsg-row--selected" : "dsg-row"}
      data-field={field.key}
      data-dragging={sortable.isDragging || undefined}
    >
      {readOnly ? null : (
        <button
          type="button"
          className="dsg-handle"
          {...sortable.attributes}
          {...sortable.listeners}
          aria-label={t("forms.designer.canvas.drag", { label: field.label || field.key })}
        >
          <span aria-hidden="true">{"⋮⋮"}</span>
        </button>
      )}
      <button
        type="button"
        className="dsg-row__main"
        data-select={field.key}
        {...(selected ? { "aria-current": "true" as const } : {})}
        onClick={() => onSelect(item)}
        onKeyDown={(e) => rowKeys(e, item, props)}
      >
        <Badge tone="outline" className="dsg-row__type">
          {t(`item_types.field_type.${field.type}`)}
        </Badge>
        <span className="dsg-row__label">{field.label}</span>
        <code className="forms-mono dsg-row__key">{field.key}</code>
        {field.required ? <span className="dsg-chip">{t("forms.designer.canvas.required")}</span> : null}
        {logic ? <span className="dsg-chip dsg-chip--logic">{t("forms.designer.canvas.logic")}</span> : null}
        <IssueCount count={counts.get(field.key)} />
      </button>
      {readOnly ? null : (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="dsg-row__delete"
          aria-label={t("forms.designer.canvas.delete", { label: field.label || field.key })}
          onClick={() => onRemove(item)}
        >
          <span aria-hidden="true">{"×"}</span>
        </Button>
      )}
    </li>
  );
}

function SectionPanel({ section, ...props }: CanvasProps & { section: FormSection }) {
  const { selection, counts, readOnly, onSelect, onRemove, onAddField } = props;
  const sortable = useSortable({ id: sectionId(section.key), disabled: readOnly, data: { kind: "section", key: section.key } });
  const drop = useDroppable({ id: sectionDropId(section.key), disabled: readOnly, data: { kind: "section-end", key: section.key } });
  const selected = selection?.kind === "section" && selection.key === section.key;
  const item = { kind: "section" as const, key: section.key };
  const logic = logicSet(section, SECTION_LOGIC_PROPS).length > 0;

  const heading = (
    <button
      type="button"
      className="dsg-section__select"
      data-select={section.key}
      {...(selected ? { "aria-current": "true" as const } : {})}
      onClick={() => onSelect(item)}
      onKeyDown={(e) => rowKeys(e, item, props)}
    >
      <span className="dsg-section__label">{section.label}</span>
      <code className="forms-mono dsg-row__key">{section.key}</code>
    </button>
  );
  const actions = (
    <>
      <span className="dsg-section__count">{t("forms.designer.canvas.fields", { count: section.fields.length })}</span>
      {logic ? <span className="dsg-chip dsg-chip--logic">{t("forms.designer.canvas.logic")}</span> : null}
      <IssueCount count={counts.get(section.key)} />
      {readOnly ? null : (
        <>
          <button
            type="button"
            className="dsg-handle"
            {...sortable.attributes}
            {...sortable.listeners}
            aria-label={t("forms.designer.canvas.drag", { label: section.label || section.key })}
          >
            <span aria-hidden="true">{"⋮⋮"}</span>
          </button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={t("forms.designer.canvas.delete", { label: section.label || section.key })}
            onClick={() => onRemove(item)}
          >
            <span aria-hidden="true">{"×"}</span>
          </Button>
        </>
      )}
    </>
  );

  return (
    <Panel
      ref={sortable.setNodeRef}
      style={{ transform: CSS.Transform.toString(sortable.transform), transition: sortable.transition }}
      heading={heading}
      headingLevel={3}
      actions={actions}
      className={selected ? "dsg-section dsg-section--selected" : "dsg-section"}
      data-section={section.key}
    >
      <SortableContext items={section.fields.map((f) => fieldId(f.key))} strategy={verticalListSortingStrategy}>
        {section.fields.length ? (
          <ul className="dsg-fields">
            {section.fields.map((field) => (
              <FieldRow key={field.key} {...props} field={field} />
            ))}
          </ul>
        ) : null}
      </SortableContext>
      <div ref={drop.setNodeRef} className={drop.isOver ? "dsg-section__drop dsg-section__drop--over" : "dsg-section__drop"}>
        {section.fields.length === 0 ? (
          <div className="dsg-section__empty">
            <p>{t("forms.designer.canvas.empty_section")}</p>
            {readOnly ? null : (
              <Button type="button" variant="secondary" onClick={() => onAddField(section.key)}>
                {t("forms.designer.canvas.add_field")}
              </Button>
            )}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

export function Canvas(props: CanvasProps) {
  const { schema, focus } = props;

  // A move re-orders DOM nodes, which drops focus; put it back on the moved item.
  useEffect(() => {
    if (!focus) return;
    // Keys match ^[a-z][a-z0-9_]*$, so they need no escaping in a selector.
    const target = document.querySelector<HTMLElement>(`[data-select="${focus.key}"]`);
    target?.focus();
  }, [focus]);

  return (
    <div className="dsg-canvas" data-testid="designer-canvas">
      <p className="dsg-canvas__hint">{t("forms.designer.canvas.hint")}</p>
      {schema.sections.length === 0 ? <p>{t("forms.designer.canvas.no_sections")}</p> : null}
      <SortableContext items={schema.sections.map((s) => sectionId(s.key))} strategy={verticalListSortingStrategy}>
        {schema.sections.map((section) => (
          <SectionPanel key={section.key} {...props} section={section} />
        ))}
      </SortableContext>
    </div>
  );
}
