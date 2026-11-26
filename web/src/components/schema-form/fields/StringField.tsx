import { escapeText } from "../../../lib/safeText";
import type { StringNode } from "../profile";
import { FieldFrame, type FieldProps } from "./FieldFrame";

function escapeMultiline(value: string): string {
  return value.split("\n").map(escapeText).join("\n");
}

// Keep the underlying value when edits leave an escaped character untouched.
function editText(previous: string, next: string, escape: (value: string) => string): string {
  const shown = escape(previous);
  if (shown === previous) return next;
  let start = 0;
  while (start < next.length && start < shown.length && next[start] === shown[start]) start += 1;
  let end = 0;
  while (end < next.length - start && end < shown.length - start &&
    next[next.length - end - 1] === shown[shown.length - end - 1]) end += 1;
  let offset = 0;
  let prefix = "";
  let suffix = "";
  for (const character of previous) {
    const escaped = escape(character);
    const suffixStart = shown.length - end - offset;
    prefix += offset + escaped.length <= start ? character : escaped.slice(0, Math.max(0, start - offset));
    suffix += suffixStart <= 0 ? character : escaped.slice(suffixStart);
    offset += escaped.length;
  }
  return prefix + next.slice(start, next.length - end) + suffix;
}

export function StringField(field: FieldProps<StringNode>) {
  const widget = field.node.widget;
  const multiline = widget === "textarea" || widget === "markdown" || widget === "code";
  const rawValue = typeof field.value === "string" ? field.value : "";
  const value = multiline ? rawValue.replaceAll("\r\n", "\n") : rawValue;
  const escape = multiline ? escapeMultiline : escapeText;
  const change = (next: string) => field.change(editText(value, multiline ? next.replaceAll("\r\n", "\n") : next, escape));
  return (
    <FieldFrame field={field}>
      {(control) => multiline ? (
        <textarea {...control} rows={4} value={escape(value)} readOnly={field.readOnly}
          spellCheck={widget !== "code"} onChange={(event) => change(event.currentTarget.value)} />
      ) : (
        <input {...control} type="text" value={escape(value)} readOnly={field.readOnly}
          spellCheck={widget !== "path"} onChange={(event) => change(event.currentTarget.value)} />
      )}
    </FieldFrame>
  );
}
