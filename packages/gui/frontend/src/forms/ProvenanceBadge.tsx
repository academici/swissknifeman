import type { Entry, Value } from "./types";

type Origin = Entry["effective"] | Entry["overridden"][number];

export function formatValue(value: Value | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return Array.isArray(value) ? JSON.stringify(value) : typeof value === "string" ? JSON.stringify(value) : String(value);
}

function where(origin: Origin): string {
  if (origin.file) return origin.line ? `${origin.file}:${origin.line}` : origin.file;
  return origin.source ?? "";
}

/** Where the effective value of a key comes from, and (expandable) what it hides. All text, no HTML. */
export function ProvenanceBadge({ entry, open = false }: { entry: Entry; open?: boolean }) {
  const { effective, overridden } = entry;
  const layer = effective.layer;
  return (
    <span className="prov" data-testid={`prov-${entry.key}`}>
      <span className={`badge layer-${layer ?? "unset"}`}>{layer ?? "unset"}</span>
      {layer !== null && <span className="prov-value">{formatValue(effective.value as Value | null)}</span>}
      {layer === "defaults" ? <span className="muted"> default</span> : where(effective) ? <code className="prov-where">{where(effective)}</code> : null}
      {overridden.length > 0 && (
        <details open={open} className="prov-overridden">
          <summary>overrides {overridden.length}</summary>
          <ul>
            {overridden.map((item, index) => (
              <li key={`${item.layer}-${index}`}>
                <span className={`badge layer-${item.layer ?? "unset"}`}>{item.layer ?? "?"}</span>{" "}
                {item.source === "_unset" ? <em>unset</em> : <span>{formatValue(item.value as Value | null)}</span>}{" "}
                {where(item) ? <code className="prov-where">{where(item)}</code> : null}
              </li>
            ))}
          </ul>
        </details>
      )}
    </span>
  );
}
