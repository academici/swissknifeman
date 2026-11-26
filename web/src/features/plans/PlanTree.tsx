import { useState } from "react";
import type { EntityPageViewItemsItem, EntityView, RevisionView } from "../../api/generated/planning";
import { useEntity, useRevision, useTreeOutline } from "../../api/hooks/planning";
import { Markdown } from "../../components/content/Markdown";
import { CopyId } from "../../components/data/CopyId";
import { EmptyState } from "../../components/data/EmptyState";
import { JsonView } from "../../components/data/JsonView";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { Tree, type TreeNode } from "../../components/viz/Tree";
import { escapeText } from "../../lib/safeText";

const groups = [
  ["requirement", "Requirements"], ["decision", "Decisions"], ["check", "Checks"],
  ["criterion", "Criteria"], ["material", "Materials"],
] as const;

function node(row: EntityPageViewItemsItem): TreeNode {
  return { id: row.entity_id, label: row.display_key === row.title ? row.title : `${row.display_key} · ${row.title}` };
}

// The tree carries nesting and order. The outline associates those display keys with immutable IDs.
function hierarchy(tree: RevisionView["tree"], rows: readonly EntityPageViewItemsItem[]) {
  const byKey = new Map(rows.map((row) => [row.display_key, row]));
  function children(values: unknown, depth: number): TreeNode[] {
    if (!Array.isArray(values)) return [];
    return values.flatMap((value: unknown) => {
      if (!value || typeof value !== "object" || !("key" in value) || typeof value.key !== "string") return [];
      const row = byKey.get(value.key);
      if (!row) return [];
      const nested = depth === 0 && "items" in value ? value.items : depth === 1 && "units" in value ? value.units : [];
      return [{ ...node(row), children: children(nested, depth + 1) }];
    });
  }
  return children(tree?.phases, 0);
}

function EntityDetails({ entity, select }: { entity: EntityView; select(ref: string): void }) {
  return <article style={{ flex: "1 1 24rem", minWidth: 0 }}>
    <h3>{escapeText(entity.display_key)} · {escapeText(entity.entity_kind)}</h3>
    <CopyId id={entity.entity_id} />
    {Object.entries(entity.document).map(([field, value]) =>
      typeof value === "string" && (field.endsWith("_md") || ["goal", "summary", "why", "statement", "text", "description", "decision", "rationale"].includes(field))
        ? <section key={field}><h4>{escapeText(field)}</h4><Markdown text={value} /></section> : null)}
    {"sections" in entity.document && entity.document.sections?.map((section) => <section key={section.id}>
      <h4>{escapeText(section.title)}</h4><Markdown text={section.text} />
    </section>)}
    <JsonView value={entity.document} />
    <dl>{Object.entries(entity.links).map(([relation, refs]: [string, readonly string[]]) => refs.length ? <div key={relation}>
      <dt>{escapeText(relation)}</dt><dd>{refs.map((ref) => <Button key={ref} onClick={() => select(ref)}>{escapeText(ref)}</Button>)}</dd>
    </div> : null)}</dl>
  </article>;
}

export function PlanTree({ planId, revisionId }: { planId: string; revisionId: string }) {
  const revision = useRevision(planId, revisionId);
  const outline = useTreeOutline(planId, revisionId);
  const [ref, setRef] = useState("");
  const entity = useEntity(planId, { revisionId }, ref);
  if (revision.error || outline.error) return <ErrorPanel error={revision.error ?? outline.error}
    onRetry={() => { void revision.refetch(); void outline.refetch(); }} />;
  if (!revision.data || !outline.data) return <Skeleton />;
  const rows = outline.data;
  if (!rows.length) return <EmptyState title="В ревизии нет сущностей" />;
  const byId = new Map<string, string>(rows.map((row) => [row.entity_id, row.display_key]));
  const select = (n: TreeNode) => setRef(byId.get(n.id) ?? "");
  return <div style={{ display: "flex", gap: "var(--space)", flexWrap: "wrap", alignItems: "flex-start" }}>
    <div>
      <Tree nodes={hierarchy(revision.data.tree, rows)} onSelect={select} />
      {groups.map(([kind, title]) => <section key={kind}>
        <h3>{title}</h3>
        <Tree nodes={rows.filter((row) => row.entity_kind === kind).map(node)} onSelect={select} />
      </section>)}
    </div>
    {ref && (entity.error ? <ErrorPanel error={entity.error} onRetry={() => void entity.refetch()} />
      : entity.data ? <EntityDetails entity={entity.data} select={setRef} /> : <Skeleton />)}
  </div>;
}
