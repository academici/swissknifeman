import { useId, useState } from "react";
import { parseSettingsScope, scopeName, settingsLevels, type SettingsLevel, type SettingsScope } from "../../api/hooks/settings";
import { escapeText } from "../../lib/safeText";
import { HostPicker } from "../data/HostPicker";
import { Button } from "../primitives/Button";

export function LevelPicker({ current, known, disabled, onSelect }: {
  current: SettingsScope;
  known: ReadonlyMap<SettingsLevel, SettingsScope>;
  disabled: boolean;
  onSelect(scope: SettingsScope, inChain: boolean): void;
}) {
  const picker = useId();
  const scopeId = useId();
  const [missingLevel, setMissingLevel] = useState<SettingsLevel>();
  const [id, setId] = useState("");
  const requested = missingLevel ? parseSettingsScope(`${missingLevel}:${id.trim()}`) : undefined;
  const choosingHost = (missingLevel ?? current.level) === "host";
  const manualScope = missingLevel && <>
    <label htmlFor={scopeId}>ID области {missingLevel}</label>{" "}
    <input id={scopeId} value={id} autoComplete="off" disabled={disabled}
      onChange={(event) => setId(event.currentTarget.value)} />
    {" "}<Button type="submit" disabled={!requested || disabled}>Открыть область</Button>
  </>;

  return (
    <form id="settings-level" onSubmit={(event) => {
      event.preventDefault();
      if (requested && !disabled) onSelect(requested, false);
    }}>
      <label htmlFor={picker}>Уровень записи</label>{" "}
      <select id={picker} value={missingLevel ?? current.level} disabled={disabled} onChange={(event) => {
        const level = settingsLevels.find((level) => level === event.currentTarget.value);
        if (!level) return;
        const target = known.get(level);
        setId("");
        setMissingLevel(target ? undefined : level);
        if (target) onSelect(target, true);
      }}>
        {settingsLevels.map((level) => {
          const scope = known.get(level);
          return <option key={level} value={level}>{escapeText(scope?.label ? `${level} · ${scope.label}` : level)}</option>;
        })}
      </select>
      {" "}<code>{escapeText(scopeName(current))}</code>
      {choosingHost && <div>
        <HostPicker disabled={disabled} value={current.level === "host" ? current.scope_id ?? "" : ""} onChange={hostId => {
          const next = parseSettingsScope(`host:${hostId}`);
          if (next && next.scope_id !== current.scope_id) onSelect(next, false);
        }} />
      </div>}
      {missingLevel && <>
        {choosingHost ? <details><summary>Указать ID хоста</summary>{manualScope}</details> : <>{" "}{manualScope}</>}
        {" "}<Button disabled={disabled} onClick={() => setMissingLevel(undefined)}>Отмена</Button>
      </>}
    </form>
  );
}
