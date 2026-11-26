import { FieldFrame, fieldId, type FieldProps } from "./FieldFrame";
import { formatValue } from "../ProvenanceBadge";
import type { Value } from "../types";

/** A leaf with a keyword the renderer does not know: shown, never edited, never an exception. */
export function ReadOnlyField(props: FieldProps) {
  const { spec, entry, value } = props;
  return (
    <FieldFrame props={{ ...props, disabled: true, reason: `unsupported: ${spec.unsupported.join(", ")}` }}>
      <code id={fieldId(entry.key)}>{formatValue(value ?? (entry.effective.value as Value | null))}</code>
    </FieldFrame>
  );
}
