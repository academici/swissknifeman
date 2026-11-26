import type { NumberNode } from "../profile";
import { FieldFrame, type FieldProps } from "./FieldFrame";

export function NumberField(field: FieldProps<NumberNode>) {
  const value = typeof field.value === "number" && Number.isFinite(field.value) ? field.value : "";
  const { schema, widget } = field.node;
  const slider = widget === "slider";
  return (
    <FieldFrame field={field}>
      {(control) => (
        <>
          <input {...control} type={slider ? "range" : "number"} value={value}
            min={slider ? Number(schema.minimum) : undefined} max={slider ? Number(schema.maximum) : undefined}
            step={slider && schema.type === "integer" ? 1 : "any"}
            disabled={slider && field.readOnly} readOnly={field.readOnly}
            onChange={(event) => {
              const number = event.currentTarget.valueAsNumber;
              field.change(Number.isFinite(number) ? number : undefined);
            }} />
          {slider && <output htmlFor={control.id}>{value}</output>}
        </>
      )}
    </FieldFrame>
  );
}
