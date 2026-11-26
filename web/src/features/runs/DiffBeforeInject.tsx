import { useState } from "react";
import { useContextDiff } from "../../api/hooks/context";
import { operatorError } from "../../api/hooks/workspace";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { escapeText } from "../../lib/safeText";

type ManifestRow = Readonly<Record<string, unknown>>;
const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/iu;
const localEpisode = /(?:^|[:/])(?:host[_-]private|local[_-]episode|episodic[_-]memory|episode)(?:$|[:/])/iu;

export function isPublicContextRow(row: ManifestRow): boolean {
  // The Hub omits local episodes at assembly. Suppress explicitly marked rows if a response includes them.
  return ![row.classification, row.source_classification, row.block_type, row.source_kind, row.source_ref, row.source]
    .some(value => typeof value === "string" && localEpisode.test(value));
}

const changes = { added: "Добавлен", removed: "Удалён", changed: "Изменён" };

function label(type: unknown) {
  switch (type) {
    case "memory": return "Память проекта";
    case "runtime_notes": return "Рекомендации для среды и модели";
    default: return typeof type === "string" ? escapeText(type) : "—";
  }
}

function tokens(value: unknown) {
  return typeof value === "number" ? value : "—";
}

function Changes({ projectId, manifestId, baseId }: { projectId: string; manifestId: string; baseId: string }) {
  // This project-scoped API compares stored Hub manifests and returns block metadata only.
  const diff = useContextDiff(projectId, manifestId, baseId);
  if (diff.isError) return <ErrorPanel error={operatorError(diff.error)} onRetry={() => void diff.refetch()} />;
  if (diff.isPending) return <Skeleton />;
  const rows = diff.data.blocks.flatMap((row, index) => {
    const { block_type, source_ref, change, tokens: counts } = row;
    if (!isPublicContextRow(row) || (change !== "added" && change !== "removed" && change !== "changed")) return [];
    const from = counts && typeof counts === "object" && "from" in counts ? counts.from : null;
    const to = counts && typeof counts === "object" && "to" in counts ? counts.to : null;
    return [{
      index, block: label(block_type), source: typeof source_ref === "string" ? escapeText(source_ref) : "—",
      change: changes[change], from: tokens(from), to: tokens(to),
    }];
  });
  return <Table rows={rows} rowKey={row => row.index} empty="Изменений в предпросмотре нет" columns={[
    { id: "change", header: "Изменение", cell: row => row.change },
    { id: "block", header: "Блок", cell: row => row.block },
    { id: "source", header: "Источник", cell: row => row.source },
    { id: "from", header: "Токены до", cell: row => row.from },
    { id: "to", header: "Токены после", cell: row => row.to },
  ]} />;
}

export function DiffBeforeInject({ projectId, manifestId }: { projectId: string; manifestId: string }) {
  const [input, setInput] = useState("");
  const [baseline, setBaseline] = useState("");
  const baseId = input.trim().toLowerCase();
  const valid = uuid.test(baseId) && baseId !== manifestId.toLowerCase();
  return <section>
    <h2>Изменения перед включением контекста</h2>
    <p>Сравните текущий манифест с базовым манифестом того же проекта.</p>
    <form onSubmit={event => {
      event.preventDefault();
      if (valid) setBaseline(baseId);
    }}>
      <label>ID базового манифеста<input value={input} onChange={event => setInput(event.currentTarget.value)} autoComplete="off" /></label>
      <Button type="submit" disabled={!valid}>Сравнить манифесты</Button>
    </form>
    {baseline && baseline === baseId && <Changes key={baseline} projectId={projectId} manifestId={manifestId} baseId={baseline} />}
  </section>;
}
