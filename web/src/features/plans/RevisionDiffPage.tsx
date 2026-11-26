import { useParams } from "react-router";
import type { SpecDiffView, SpecDiffViewPlanFieldsItem } from "../../api/generated/planning";
import { planPath, useDiff, usePlan } from "../../api/hooks/planning";
import { SafeLink } from "../../components/content/SafeLink";
import { DataList } from "../../components/data/DataList";
import { KeyValue } from "../../components/data/KeyValue";
import { EmptyState } from "../../components/data/EmptyState";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Skeleton } from "../../components/primitives/Skeleton";
import { DiffView, type DiffKind } from "../../components/viz/DiffView";

function fieldChange(field: SpecDiffViewPlanFieldsItem) {
  return {
    id: field.pointer, label: field.pointer,
    kind: ({ add: "added", remove: "removed", replace: "changed" } as const)[field.op],
    ...(field.op === "add" ? {} : { before: JSON.stringify(field.before) }),
    ...(field.op === "remove" ? {} : { after: JSON.stringify(field.after) }),
  };
}

function RevisionSource({ source, planId }: { source: SpecDiffView["from"]; planId: string }) {
  const id = source.revision_id ?? source.id;
  if (typeof id !== "string") return <>Пустая база</>;
  const label = typeof source.revision_no === "number" ? `r${source.revision_no}` : id;
  return <SafeLink href={planPath(planId) + "/revisions/" + encodeURIComponent(id)}>{label}</SafeLink>;
}

function RevisionDiff({ diff, planId }: { diff: SpecDiffView; planId: string }) {
  const entities = diff.entities.flatMap((entity) => {
    const kinds: DiffKind[] = [entity.change];
    if (entity.rekeyed) kinds.push("rekeyed");
    if (entity.moved) kinds.push("moved");
    const fields = entity.fields.map((field) =>
      `${field.pointer} (${field.op}): ${JSON.stringify(field.before)} → ${JSON.stringify(field.after)}`);
    return kinds.map((kind) => ({
      kind, id: entity.entity_id,
      label: [entity.entity_kind, entity.entity_id, ...(kind === entity.change ? fields : [])].join(" · "),
      ...(entity.key_before === null ? {} : { before: entity.key_before }),
      ...(entity.key_after === null ? {} : { after: entity.key_after }),
    }));
  });
  return <>
    <DataList>
      <KeyValue label="Исходная версия" value={<RevisionSource source={diff.from} planId={planId} />} />
      <KeyValue label="Исходный digest" value={diff.from_digest} />
      <KeyValue label="Целевая версия" value={<RevisionSource source={diff.to} planId={planId} />} />
      <KeyValue label="Целевой digest" value={diff.to_digest} />
      {Object.entries(diff.summary).map(([key, count]) => <KeyValue key={key} label={key} value={count} />)}
    </DataList>
    {diff.plan_fields.length > 0 && <section><h2>Поля плана</h2><DiffView changes={diff.plan_fields.map(fieldChange)} /></section>}
    {entities.length > 0 && <section><h2>Сущности</h2><DiffView changes={entities} /></section>}
    {!diff.plan_fields.length && !entities.length && <EmptyState title="Изменений нет" />}
  </>;
}

export default function RevisionDiffPage() {
  const { planId = "", revisionId = "", againstId } = useParams();
  usePlan(planId);
  const diff = useDiff(planId, { revisionId }, againstId);
  return <section><h1>Сравнение ревизий</h1>
    {diff.error ? <ErrorPanel error={diff.error} onRetry={() => void diff.refetch()} /> : diff.data ? <RevisionDiff diff={diff.data} planId={planId} /> : <Skeleton />}
  </section>;
}
