import { useState } from "react";
import { parseInteger, parseNumber } from "../draft";
import type { Scalar } from "../types";
import { FieldFrame, fieldId, type FieldProps } from "./FieldFrame";

function convert(texts: string[], itemType: string | undefined): Scalar[] | null {
  const out: Scalar[] = [];
  for (const text of texts) {
    if (itemType === "integer" || itemType === "number") {
      const parsed = itemType === "integer" ? parseInteger(text) : parseNumber(text);
      if (parsed === null) return null;
      out.push(parsed);
    } else if (itemType === "boolean") {
      out.push(text === "true");
    } else {
      out.push(text);
    }
  }
  return out;
}

/** A list of scalars: one text input per item, add and remove. */
export function ScalarListField(props: FieldProps) {
  const { spec, entry, value, disabled } = props;
  const [stored, setLocal] = useState<string[] | null>(null);
  // the local texts are valid only while they still describe the draft value: after a discard or an apply the value
  // changes under them and they must not bring back what was dropped
  const storedValue = stored === null ? null : convert(stored, spec.itemType);
  const local = stored !== null && storedValue !== null && JSON.stringify(storedValue) !== JSON.stringify(value ?? []) ? null : stored;
  if (stored !== null && local === null) setLocal(null);
  const texts = local ?? (Array.isArray(value) ? value.map(String) : []);
  const error = local !== null && convert(local, spec.itemType) === null ? `an item is not ${spec.itemType === "integer" ? "an integer" : "a number"}` : null;

  function update(next: string[]) {
    setLocal(next);
    const converted = convert(next, spec.itemType);
    if (converted !== null) props.onSet(converted);
  }

  return (
    <FieldFrame props={props} error={error}>
      <div className="cfg-list" id={fieldId(entry.key)}>
        {texts.map((text, index) => (
          <div key={index} className="cfg-list-item">
            <input type="text" aria-label={`${entry.key} item ${index + 1}`} disabled={disabled} value={text}
                   onChange={(event) => update(texts.map((item, at) => (at === index ? event.target.value : item)))} />
            <button type="button" disabled={disabled} aria-label={`Remove ${entry.key} item ${index + 1}`}
                    onClick={() => update(texts.filter((_item, at) => at !== index))}>
              Remove
            </button>
          </div>
        ))}
        <button type="button" disabled={disabled} onClick={() => update([...texts, ""])}>
          Add item
        </button>
      </div>
    </FieldFrame>
  );
}
