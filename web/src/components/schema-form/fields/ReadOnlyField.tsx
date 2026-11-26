import { escapeText } from "../../../lib/safeText";
import type { UnsupportedNode } from "../profile";
import { FieldFrame, type FieldProps } from "./FieldFrame";

function formattedJson(value: unknown): string {
  try {
    // Preserve only JSON.stringify's structural line breaks.
    return (JSON.stringify(value, null, 2) ?? "—").split("\n").map(escapeText).join("\n");
  } catch {
    return "JSON недоступен";
  }
}

export function ReadOnlyField(field: FieldProps<UnsupportedNode>) {
  return (
    <FieldFrame field={field} group>
      {() => (
        <>
          <pre tabIndex={0}><code>{formattedJson(field.node.redact(field.value))}</code></pre>
          <p>Не поддерживается ({escapeText(field.node.keywords.join(", "))}), редактируйте через import.</p>
        </>
      )}
    </FieldFrame>
  );
}
