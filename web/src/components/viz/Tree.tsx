import { escapeText } from "../../lib/safeText";
import { StatusBadge } from "../primitives/StatusBadge";

export interface TreeNode {
  readonly id: string;
  readonly label: string;
  readonly status?: string;
  readonly children?: readonly TreeNode[];
}

export function Tree({ nodes, onSelect }: {
  nodes: readonly TreeNode[];
  onSelect: (node: TreeNode) => void;
}) {
  return (
    <ul className="tree">
      {nodes.map((node) => {
        const label = escapeText(node.label);
        const badge = node.status === undefined ? null : <StatusBadge status={node.status} />;
        if (!node.children?.length) {
          return <li key={node.id}><button type="button" onClick={() => onSelect(node)}>{label}</button> {badge}</li>;
        }
        return (
          <li key={node.id}>
            <details>
              <summary>{label} {badge}</summary>
              <button type="button" onClick={() => onSelect(node)}>Открыть {label}</button>
              <Tree nodes={node.children} onSelect={onSelect} />
            </details>
          </li>
        );
      })}
    </ul>
  );
}
