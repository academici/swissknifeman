import { FieldFrame, fieldId, type FieldProps } from "./FieldFrame";

export function EnumField(props: FieldProps) {
  const { spec, entry, value, disabled } = props;
  const options = spec.enum ?? [];
  return (
    <FieldFrame props={props}>
      <select id={fieldId(entry.key)} disabled={disabled} value={value === null ? "" : String(value)}
              onChange={(event) => {
                const chosen = options.find((option) => String(option) === event.target.value);
                if (chosen === undefined) props.onUnset();
                else props.onSet(chosen);
              }}>
        <option value="">—</option>
        {options.map((option) => (
          <option key={String(option)} value={String(option)}>
            {String(option)}
          </option>
        ))}
      </select>
    </FieldFrame>
  );
}
