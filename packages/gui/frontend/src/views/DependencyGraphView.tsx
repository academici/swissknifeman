import type { ViewData } from "../contracts";
import { StatusBadge } from "./common";

type Graph = Extract<ViewData, { view: "dependency-graph" }>;

const COL_W = 220;
const ROW_H = 56;
const NODE_W = 180;
const NODE_H = 36;
const PAD = 16;

function clip(text: string, max = 26): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** Nodes in one column per `group` (first appearance order), straight SVG edges; no external library, linear in
 * nodes and edges. A table "depends on" repeats the graph as text. */
export function DependencyGraphView({ data }: { data: Graph }) {
  const groups: string[] = [];
  const rows = new Map<string, number>();
  const place = new Map<string, { x: number; y: number }>();
  const nodes = [];
  for (const node of data.nodes) {
    if (place.has(node.id)) continue; // a repeated id keeps its first node
    const group = node.group ?? "";
    let column = groups.indexOf(group);
    if (column < 0) {
      groups.push(group);
      column = groups.length - 1;
    }
    const row = rows.get(group) ?? 0;
    rows.set(group, row + 1);
    place.set(node.id, { x: PAD + column * COL_W, y: PAD + row * ROW_H });
    nodes.push(node);
  }
  const edges = data.edges.filter((edge) => place.has(edge.from) && place.has(edge.to));
  const width = PAD * 2 + Math.max(groups.length, 1) * COL_W - (COL_W - NODE_W);
  const height = PAD * 2 + Math.max(...Array.from(rows.values()), 1) * ROW_H - (ROW_H - NODE_H);
  const needs = new Map<string, string[]>();
  const related = new Map<string, string[]>();
  for (const edge of edges) {
    const table = edge.kind === "blocks" ? needs : related;
    table.set(edge.to, [...(table.get(edge.to) ?? []), edge.from]);
  }
  return (
    <div className="dependency-graph">
      {nodes.length > 0 && (
        <svg role="img" aria-label={`Dependency graph, ${nodes.length} nodes, ${edges.length} edges`} width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          <defs>
            <marker id="graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="graph-arrowhead" />
            </marker>
          </defs>
          {edges.map((edge, index) => {
            const from = place.get(edge.from)!;
            const to = place.get(edge.to)!;
            const sameColumn = from.x === to.x;
            const x1 = sameColumn ? from.x + NODE_W / 2 : from.x + NODE_W;
            const y1 = sameColumn ? (from.y < to.y ? from.y + NODE_H : from.y) : from.y + NODE_H / 2;
            const x2 = sameColumn ? to.x + NODE_W / 2 : to.x;
            const y2 = sameColumn ? (from.y < to.y ? to.y : to.y + NODE_H) : to.y + NODE_H / 2;
            return (
              <line
                key={`${edge.from}-${edge.to}-${edge.kind}-${index}`}
                className={`graph-edge graph-edge-${edge.kind}`}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                strokeDasharray={edge.kind === "related" ? "5 4" : undefined}
                markerEnd="url(#graph-arrow)"
              >
                <title>{`${edge.from} ${edge.kind === "blocks" ? "blocks" : "relates to"} ${edge.to}`}</title>
              </line>
            );
          })}
          {nodes.map((node) => {
            const at = place.get(node.id)!;
            return (
              <g key={node.id} className={`graph-node status-${node.status ?? "unknown"}`} transform={`translate(${at.x} ${at.y})`}>
                <title>{`${node.label} (${node.status ?? "unknown"})`}</title>
                <rect width={NODE_W} height={NODE_H} rx={6} />
                <text x={8} y={15}>{clip(node.label)}</text>
                <text x={8} y={29} className="graph-status">{node.status ?? "unknown"}</text>
              </g>
            );
          })}
        </svg>
      )}
      {nodes.length === 0 && <div className="muted">Nothing to show.</div>}
      {nodes.length > 0 && (
        <table className="table graph-table">
          <caption className="muted">Dependencies as text</caption>
          <thead>
            <tr>
              <th>Item</th>
              <th>Status</th>
              <th>Depends on</th>
              <th>Related</th>
            </tr>
          </thead>
          <tbody>
            {nodes.map((node) => (
              <tr key={node.id}>
                <td>{node.label}</td>
                <td>
                  <StatusBadge status={node.status ?? "unknown"} />
                </td>
                <td>{(needs.get(node.id) ?? []).join(", ") || "—"}</td>
                <td>{(related.get(node.id) ?? []).join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
