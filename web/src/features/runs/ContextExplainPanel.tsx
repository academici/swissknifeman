import { useState } from "react";
import { useParams } from "react-router";
import { useContextManifest, useContextText } from "../../api/hooks/context";
import { field, useStep } from "../../api/hooks/execution";
import { useScope } from "../../app/providers/ScopeProvider";
import { CodeBlock } from "../../components/content/CodeBlock";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";
import { DiffBeforeInject, isPublicContextRow } from "./DiffBeforeInject";
import { FileDownload } from "./StepPanel";

function ContextText({ projectId, manifestId, position }: { projectId: string; manifestId: string; position?: number }) {
  const text = useContextText(projectId, manifestId, position);
  if (text.isError) return <ErrorPanel error={text.error} onRetry={() => { void text.refetch(); }} />;
  if (!text.data) return <Skeleton />;
  if (!text.data.available) return <p>Текст недоступен.</p>;
  if (text.data.text !== null) return <CodeBlock text={text.data.text} />;
  return text.data.prompt_file_version_id
    ? <FileDownload versionId={text.data.prompt_file_version_id} label="Скачать сохранённый промпт" />
    : <p>Текст недоступен.</p>;
}

function Manifest({ projectId, manifestId }: { projectId: string; manifestId: string }) {
  const manifest = useContextManifest(projectId, manifestId);
  const [text, setText] = useState<number | "prompt" | null>(null);
  if (manifest.isError) return <ErrorPanel error={manifest.error} onRetry={() => { void manifest.refetch(); }} />;
  if (!manifest.data) return <Skeleton />;
  const view = manifest.data;
  const rows = view.rows.filter(isPublicContextRow);
  return <>
    <StatusBadge status={view.state} />
    <dl>
      <KeyValue label="Манифест" value={manifestId} />
      <KeyValue label="Среда" value={field(view.route.runtime_id)} />
      <KeyValue label="Модель" value={field(view.route.model)} />
      <KeyValue label="Режим" value={field(view.mode)} />
    </dl>
    <DiffBeforeInject projectId={projectId} manifestId={manifestId} />
    <Table rows={rows.map((row, index) => ({ row, index }))} rowKey={({ index }) => index} columns={[
      { id: "type", header: "Блок", cell: ({ row }) => escapeText(field(row.block_type)) },
      { id: "source", header: "Источник", cell: ({ row }) => escapeText(field(row.source)) },
      { id: "version", header: "Версия", cell: ({ row }) => escapeText(field(row.source_version ?? row.version)) },
      { id: "digest", header: "Дайджест", cell: ({ row }) => <code>{escapeText(field(row.digest))}</code> },
      { id: "tokens", header: "Токены", cell: ({ row }) => escapeText(field(row.tokens)) },
      { id: "included", header: "Включён", cell: ({ row }) => escapeText(field(row.included)) },
      { id: "reason", header: "Причина", cell: ({ row }) => escapeText(field(row.reason, "—")) },
      { id: "text", header: "Текст", cell: ({ row }) => {
        const position = row.pos;
        return row.included === true && typeof position === "number" && <Button onClick={() => setText(position)}>
          Текст блока {position}
        </Button>;
      } },
    ]} />
    <Button onClick={() => setText("prompt")}>Сохранённый промпт</Button>
    {(text === "prompt" || (text !== null && rows.some(row => row.pos === text && row.included === true))) && <section>
      <h2>{text === "prompt" ? "Материалы промпта" : `Текст блока ${text}`}</h2>
      {text === "prompt" ? <ContextText projectId={projectId} manifestId={manifestId} />
        : <ContextText projectId={projectId} manifestId={manifestId} position={text} />}
    </section>}
    <JsonView value={{
      budgets: view.budgets, totals: view.totals, excluded: view.excluded?.filter(isPublicContextRow), skills_trace: view.skills_trace,
      runtime_self_loads: view.runtime_self_loads, host_facts: view.host_facts, diagnostics: view.diagnostics,
    }} />
  </>;
}

export default function ContextExplainPanel() {
  const { stepId = "" } = useParams();
  const { scope: { projectId } } = useScope();
  const step = useStep(stepId);
  return <section>
    <h1>Контекст шага</h1>
    {step.isError ? <ErrorPanel error={step.error} onRetry={() => { void step.refetch(); }} />
      : !step.data ? <Skeleton />
      : !step.data.context_manifest_id ? <p>Манифест контекста недоступен.</p>
      : !projectId ? <p>Выберите проект шага в переключателе области.</p>
      : <Manifest key={`${projectId}:${step.data.context_manifest_id}`} projectId={projectId} manifestId={step.data.context_manifest_id} />}
  </section>;
}
