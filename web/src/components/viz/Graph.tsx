import { escapeText } from "../../lib/safeText";
import { StatusBadge } from "../primitives/StatusBadge";

interface Node {
  readonly id: string;
  readonly label: string;
  readonly status: string;
}

interface Edge {
  readonly from: string;
  readonly to: string;
}

export function Graph({ nodes, edges, onSelect }: {
  nodes: readonly Node[];
  edges: readonly Edge[];
  onSelect(id: string): void;
}) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const parents = new Map<string, string[]>();
  for (const { from, to } of edges) {
    if (!byId.has(from) || !byId.has(to)) continue;
    const previous = parents.get(to) ?? [];
    previous.push(from);
    parents.set(to, previous);
  }

  const remaining = new Set(byId.keys());
  const layers: string[][] = [];
  while (remaining.size > 0) {
    const layer = [...remaining].filter((id) => (parents.get(id) ?? []).every((parent) => !remaining.has(parent)));
    if (!layer.length) {
      layers.push([...remaining]);
      break;
    }
    layers.push(layer);
    for (const id of layer) remaining.delete(id);
  }

  return (
    <ol className="graph" aria-label="Зависимости задач">
      {layers.map((layer, index) => (
        <li key={index}>
          <ul className="graph-layer">
            {layer.map((id) => {
              const node = byId.get(id);
              if (!node) return null;
              const dependencies = (parents.get(id) ?? []).map((parent) => byId.get(parent)?.label ?? parent);
              return (
                <li key={id}>
                  <button type="button" onClick={() => onSelect(id)}>{escapeText(node.label)}</button>{" "}
                  <StatusBadge status={node.status} />
                  {dependencies.length > 0 && <p>Зависит от {escapeText(dependencies.join(", "))}</p>}
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ol>
  );
}
