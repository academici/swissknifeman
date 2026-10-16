import { FieldFrame, fieldId, type FieldProps } from "./FieldFrame";

export function StringField(props: FieldProps) {
  const { entry, value, disabled } = props;
  return (
    <FieldFrame props={props}>
      <input id={fieldId(entry.key)} type="text" disabled={disabled} value={typeof value === "string" ? value : ""}
             placeholder={typeof entry.effective.value === "string" ? entry.effective.value : ""}
             onChange={(event) => (event.target.value === "" ? props.onUnset() : props.onSet(event.target.value))} />
    </FieldFrame>
  );
}
