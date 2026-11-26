import { useState } from "react";
import type { SecretNode } from "../profile";
import { isSecretReference, secretFormatHint } from "../values";
import { FieldFrame, type FieldProps } from "./FieldFrame";

function isReferencePrefix(value: string): boolean {
  if ("secret://".startsWith(value)) return true;
  if (!value.startsWith("secret://") || /[\s\p{Cc}\p{Bidi_Control}]/u.test(value)) return false;
  const path = value.slice("secret://".length);
  return ["env/", "file/", "keyring/"].some((prefix) => prefix.startsWith(path)) ||
    /^keyring\/[A-Za-z0-9._-]{1,128}\/?$/u.test(path);
}

export function SecretRefField(field: FieldProps<SecretNode>) {
  const reference = isSecretReference(field.value) ? field.value : "";
  const [draft, setDraft] = useState<{ source: string; prefix: string; invalid: boolean }>();
  const current = draft?.source === reference ? draft : undefined;
  return (
    <FieldFrame field={field} hints={current?.invalid ? [secretFormatHint] : []}>
      {(control) => (
        <input {...control} type="password" value={current?.prefix ?? reference} readOnly={field.readOnly}
          autoComplete="off" spellCheck={false} onChange={(event) => {
            const value = event.currentTarget.value;
            if (isSecretReference(value) || value === "") {
              setDraft(undefined);
              field.change(value || undefined);
            } else if (isReferencePrefix(value)) {
              setDraft({ source: reference, prefix: value, invalid: true });
            } else {
              setDraft({ source: reference, prefix: current?.prefix ?? reference, invalid: true });
            }
          }} />
      )}
    </FieldFrame>
  );
}
