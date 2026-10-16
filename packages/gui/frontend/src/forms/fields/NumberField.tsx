import { useState } from "react";
import { parseInteger, parseNumber } from "../draft";
import { FieldFrame, fieldId, type FieldProps } from "./FieldFrame";

/** Integer and number: the text is parsed by type only; a text that is not a number makes no operation. */
export function NumberField(props: FieldProps) {
  const { spec, entry, value, disabled } = props;
  const integer = spec.type === "integer";
  const [text, setText] = useState<string | null>(null);
  const shown = text ?? (typeof value === "number" ? String(value) : "");
  const error = text !== null && text !== "" && (integer ? parseInteger(text) : parseNumber(text)) === null
    ? `not ${integer ? "an integer" : "a number"}` : null;

  function change(next: string) {
    setText(next);
    if (next.trim() === "") return props.onUnset();
    const parsed = integer ? parseInteger(next) : parseNumber(next);
    if (parsed !== null) props.onSet(parsed);
  }

  return (
    <FieldFrame props={props} error={error}>
      <input id={fieldId(entry.key)} type="text" inputMode={integer ? "numeric" : "decimal"} disabled={disabled} value={shown}
             placeholder={typeof entry.effective.value === "number" ? String(entry.effective.value) : ""}
             onChange={(event) => change(event.target.value)} onBlur={() => setText(null)} />
    </FieldFrame>
  );
}
