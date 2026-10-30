import { Label } from "@aip/ui";
import { useId } from "react";
import { GroupFrame, NotAnswered, ReadOnlyFrame, type FieldProps } from "./FieldFrame";

/**
 * `boolean` → two radio buttons (yes / no) in a radiogroup, so "not answered" (neither checked)
 * stays distinct from "no".
 */
export function BooleanField({ value, onChange, t, readOnly, frame }: FieldProps) {
  const id = useId();
  if (readOnly) {
    return (
      <ReadOnlyFrame frame={frame}>
        {value === true ? (
          <span>{t("forms.renderer.yes")}</span>
        ) : value === false ? (
          <span>{t("forms.renderer.no")}</span>
        ) : (
          <NotAnswered t={t} />
        )}
      </ReadOnlyFrame>
    );
  }
  const choices = [
    { answer: true, key: "yes", label: t("forms.renderer.yes") },
    { answer: false, key: "no", label: t("forms.renderer.no") },
  ];
  return (
    <GroupFrame frame={frame} role="radiogroup">
      <div className="aip-form-renderer__choices">
        {choices.map((choice) => {
          const radioId = `${id}-${choice.key}`;
          return (
            <span key={choice.key} className="aip-form-renderer__choice">
              <input
                id={radioId}
                type="radio"
                className="aip-form-renderer__radio"
                name={id}
                checked={value === choice.answer}
                onChange={() => onChange(choice.answer)}
              />
              <Label htmlFor={radioId}>{choice.label}</Label>
            </span>
          );
        })}
      </div>
    </GroupFrame>
  );
}
