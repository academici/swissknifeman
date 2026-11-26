import { escapeText } from "../../../lib/safeText";
import type { EnumNode } from "../profile";
import { jsonEqual } from "../values";
import { FieldFrame, type FieldProps } from "./FieldFrame";

function optionLabel(value: unknown): string {
  return escapeText(typeof value === "string" ? value : JSON.stringify(value) ?? "");
}

export function EnumField(field: FieldProps<EnumNode>) {
  const { options, widget } = field.node;
  const selected = options.findIndex((option) => jsonEqual(option, field.value));
  if (widget === "select") {
    return (
      <FieldFrame field={field}>
        {(control) => (
          <select {...control} value={selected < 0 ? "" : selected} disabled={field.readOnly}
            onChange={(event) => field.change(options[Number(event.currentTarget.value)])}>
            {selected < 0 && <option value="" disabled>Выберите значение</option>}
            {options.map((option, index) => <option key={index} value={index}>{optionLabel(option)}</option>)}
          </select>
        )}
      </FieldFrame>
    );
  }
  return (
    <FieldFrame field={field} group>
      {(control) => options.map((option, index) => {
        const id = `${control.id}-${index}`;
        return (
          <div key={index}>
            <input {...control} id={id} type="radio" name={control.id} value={index}
              checked={selected === index} disabled={field.readOnly} aria-required={field.required || undefined}
              onChange={() => field.change(option)} />
            <label htmlFor={id}>{optionLabel(option)}</label>
          </div>
        );
      })}
    </FieldFrame>
  );
}
