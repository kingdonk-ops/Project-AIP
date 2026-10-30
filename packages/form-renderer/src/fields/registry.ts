import { createElement, type ComponentType, type ReactElement } from "react";
import type { FieldType } from "../logic/types";
import { BooleanField } from "./BooleanField";
import { DropdownField, MultiSelectField } from "./ChoiceFields";
import { DateField } from "./DateField";
import type { FieldProps } from "./FieldFrame";
import { MeasurementField } from "./MeasurementField";
import { PhotoField, SignatureField } from "./MediaFields";
import { NumberField } from "./NumberField";
import { ReferenceField } from "./ReferenceFields";
import { TextField } from "./TextField";

/** Field-type registry key (ITEMTYPES-01) → the component that renders it. */
export const FIELD_COMPONENTS: Readonly<Record<FieldType, ComponentType<FieldProps>>> = {
  text: TextField,
  number: NumberField,
  decimal: NumberField,
  date: DateField,
  dropdown: DropdownField,
  multi_select: MultiSelectField,
  measurement: MeasurementField,
  boolean: BooleanField,
  photo: PhotoField,
  signature: SignatureField,
  asset_ref: ReferenceField,
  user_ref: ReferenceField,
};

/** The component for a type, or `null` for a type this renderer does not know (e.g. `gps`). */
export function fieldComponent(type: string): ComponentType<FieldProps> | null {
  return Object.hasOwn(FIELD_COMPONENTS, type) ? FIELD_COMPONENTS[type as FieldType] : null;
}

/** Renders `props.field` with its registered component; `null` for an unknown type. */
export function renderField(props: FieldProps): ReactElement | null {
  const component = fieldComponent(props.field.type);
  return component ? createElement(component, props) : null;
}
