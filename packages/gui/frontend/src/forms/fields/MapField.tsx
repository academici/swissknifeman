import { useState } from "react";
import { clearOp, unsetValue } from "../draft";
import type { FormContext } from "../formContext";
import { entryLeaves, type MapSpec } from "../profile";
import { LeafField } from "./LeafField";

/** A dictionary table: its entries as groups of fields, add an entry by name, remove one (unset of its keys). */
export function MapField({ spec, ctx }: { spec: MapSpec; ctx: FormContext }) {
  const [added, setAdded] = useState<string[]>([]);
  const [name, setName] = useState("");
  const listed = ctx.view.maps.find((map) => map.key === spec.key)?.entries ?? [];
  const names = [...new Set([...listed, ...added])];
  const record = ctx.view.layers.find((layer) => layer.name === ctx.layer);
  const writable = Boolean(record?.writable);

  function remove(entry: string) {
    let draft = ctx.draft;
    if (draft) {
      for (const leaf of entryLeaves(spec, entry)) draft = draft.base[leaf.key] != null ? unsetValue(draft, leaf.key) : clearOp(draft, leaf.key);
      ctx.onDraft(draft);
    }
    setAdded(added.filter((candidate) => candidate !== entry));
  }

  return (
    <fieldset className="cfg-map" data-key={spec.key}>
      <legend>{spec.key}</legend>
      {spec.description ? <div className="muted">{spec.description}</div> : null}
      {names.length === 0 ? <div className="muted">No entries.</div> : null}
      {names.map((entry) => (
        <fieldset key={entry} className="cfg-entry" data-entry={entry}>
          <legend>{entry}</legend>
          {entryLeaves(spec, entry).map((leaf) => (
            <LeafField key={leaf.key} spec={leaf} ctx={ctx} />
          ))}
          <button type="button" disabled={!writable} aria-label={`Remove entry ${spec.key}.${entry}`} onClick={() => remove(entry)}>
            Remove entry
          </button>
        </fieldset>
      ))}
      <div className="cfg-add">
        <input type="text" aria-label={`New entry of ${spec.key}`} value={name} disabled={!writable}
               placeholder={spec.pattern ? `name, pattern ${spec.pattern}` : "name"} onChange={(event) => setName(event.target.value)} />
        <button type="button" disabled={!writable || name === "" || names.includes(name)}
                onClick={() => { setAdded([...added, name]); setName(""); }}>
          Add entry
        </button>
      </div>
    </fieldset>
  );
}
