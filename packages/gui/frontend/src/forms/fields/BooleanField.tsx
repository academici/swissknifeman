import { FieldFrame, fieldId, type FieldProps } from "./FieldFrame";

export function BooleanField(props: FieldProps) {
  const { entry, value, disabled } = props;
  return (
    <FieldFrame props={props}>
      <input id={fieldId(entry.key)} type="checkbox" disabled={disabled}
             checked={value === true || (value === null && entry.effective.value === true)}
             onChange={(event) => props.onSet(event.target.checked)} />
    </FieldFrame>
  );
}
