import type { BooleanNode } from "../profile";
import { FieldFrame, type FieldProps } from "./FieldFrame";

export function BooleanField(field: FieldProps<BooleanNode>) {
  return (
    <FieldFrame field={field}>
      {({ "aria-required": required, ...control }) => (
        <input {...control} type="checkbox" role={field.node.widget === "checkbox" ? undefined : "switch"}
          aria-required={required} checked={field.value === true} disabled={field.readOnly}
          onChange={(event) => field.change(event.currentTarget.checked)} />
      )}
    </FieldFrame>
  );
}
