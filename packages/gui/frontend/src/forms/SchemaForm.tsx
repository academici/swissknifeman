import { useMemo } from "react";
import { LeafField } from "./fields/LeafField";
import { MapField } from "./fields/MapField";
import type { FormContext } from "./formContext";
import { parseSchema, type NodeSpec } from "./profile";

function Node({ node, ctx }: { node: NodeSpec; ctx: FormContext }) {
  if (node.kind === "leaf") return <LeafField spec={node} ctx={ctx} />;
  if (node.kind === "map") return <MapField spec={node} ctx={ctx} />;
  return (
    <fieldset className="cfg-table" data-key={node.key}>
      <legend>{node.title ?? node.key}</legend>
      {node.description ? <div className="muted">{node.description}</div> : null}
      {node.unsupported.length > 0 ? <div className="muted">unsupported: {node.unsupported.join(", ")}</div> : null}
      {node.children.map((child) => (
        <Node key={child.key} node={child} ctx={ctx} />
      ))}
    </fieldset>
  );
}

/** The form of a module schema (the closed profile of aicore) over a config-view: one field per leaf. */
export function SchemaForm(ctx: FormContext) {
  const nodes = useMemo(() => parseSchema(ctx.view.schema), [ctx.view.schema]);
  return (
    <form className="schema-form" onSubmit={(event) => event.preventDefault()}>
      {nodes.map((node) => (
        <Node key={node.key} node={node} ctx={ctx} />
      ))}
    </form>
  );
}
