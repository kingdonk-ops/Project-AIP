/**
 * The attribute JSON editor (ITEMTYPES-03): a labelled monospace textarea holding an item type's
 * draft `attributes` array, the client hints from `attributes.ts`, and the issues the server
 * reported (422 `ATTRIBUTES_INVALID`), each with its term text and its path in mono. Selecting an
 * issue or hint puts the caret on that attribute in the text. ADR 0007: no visual designer in R1.
 */
import { Label } from "@aip/ui";
import { useId, useRef, type ReactNode } from "react";
import { t } from "../shell/t";
import { elementOffset, issueIndex, type AttributeHint, type ParseError } from "./attributes";

export interface AttributeIssue {
  path: string;
  code: string;
}

export interface AttributeJsonEditorProps {
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  parseError: ParseError | null;
  hints: readonly AttributeHint[];
  issues: readonly AttributeIssue[];
  /** The editor's buttons (Create draft, Format, Save draft, ...). */
  actions?: ReactNode;
  /** Shown under the label (e.g. "the published attributes, read-only"). */
  note?: string;
}

export function AttributeJsonEditor({ value, onChange, readOnly, parseError, hints, issues, actions, note }: AttributeJsonEditorProps) {
  const id = useId();
  const area = useRef<HTMLTextAreaElement>(null);

  function focusAttribute(index: number | undefined) {
    const el = area.current;
    if (!el) return;
    const offset = index === undefined ? 0 : elementOffset(value, index);
    el.focus();
    el.setSelectionRange(offset, offset);
  }

  return (
    <div className="item-types-json">
      <Label htmlFor={`${id}-text`} className="item-types-json__label">
        {t("item_types.editor.label")}
      </Label>
      {note ? (
        <p id={`${id}-note`} className="item-types-json__note">
          {note}
        </p>
      ) : null}
      {actions ? <div className="item-types-json__actions">{actions}</div> : null}
      <textarea
        ref={area}
        id={`${id}-text`}
        className="item-types-json__text item-types-mono"
        value={value}
        readOnly={readOnly}
        spellCheck={false}
        rows={20}
        aria-invalid={parseError !== null || issues.length > 0}
        {...(note ? { "aria-describedby": `${id}-note` } : {})}
        onChange={(e) => onChange(e.target.value)}
      />
      {hints.length > 0 ? (
        <section aria-labelledby={`${id}-hints`} className="item-types-json__hints">
          <h3 id={`${id}-hints`}>{t("item_types.editor.hints")}</h3>
          <ul>
            {hints.map((hint, i) => (
              <li key={`${hint.key}-${hint.index ?? "all"}-${i}`}>
                <button type="button" className="item-types-json__issue" onClick={() => focusAttribute(hint.index)}>
                  <span>{t(hint.key)}</span>
                  {hint.index !== undefined ? <code className="item-types-mono">{`attributes[${hint.index}]`}</code> : null}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {issues.length > 0 ? (
        <section aria-labelledby={`${id}-issues`} className="item-types-json__issues" role="alert">
          <h3 id={`${id}-issues`}>{t("item_types.editor.issues")}</h3>
          <ul>
            {issues.map((issue, i) => (
              <li key={`${issue.path}-${issue.code}-${i}`}>
                <button type="button" className="item-types-json__issue" onClick={() => focusAttribute(issueIndex(issue.path))}>
                  <span>{t(`item_types.issue.${issue.code.toLowerCase()}`)}</span>
                  <code className="item-types-mono">{issue.path}</code>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
