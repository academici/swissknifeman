import { FieldFrame, fieldId, type FieldProps } from "./FieldFrame";

const SCHEMES = ["env", "keyring"] as const;
const REF = /^(env|keyring):\/\/(.*)$/;

/** A secret key holds a reference `<scheme>://<name>`, never a value; only the schemes env and keyring are offered. */
export function SecretRefField(props: FieldProps) {
  const { entry, value, disabled } = props;
  const text = typeof value === "string" ? value : "";
  const match = REF.exec(text);
  const foreign = text !== "" && match === null;
  const scheme = match?.[1] ?? "env";
  const name = match?.[2] ?? "";
  const set = (nextScheme: string, nextName: string) => (nextName === "" ? props.onUnset() : props.onSet(`${nextScheme}://${nextName}`));
  return (
    <FieldFrame props={props} error={foreign ? "not a reference of the form env://NAME or keyring://NAME" : null}>
      {foreign ? (
        <code>{text}</code>
      ) : (
        <span className="cfg-secret">
          <select aria-label={`${entry.key} scheme`} disabled={disabled} value={scheme} onChange={(event) => set(event.target.value, name)}>
            {SCHEMES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <span>://</span>
          <input id={fieldId(entry.key)} type="text" disabled={disabled} value={name} autoComplete="off" spellCheck={false}
                 onChange={(event) => set(scheme, event.target.value)} />
        </span>
      )}
    </FieldFrame>
  );
}
