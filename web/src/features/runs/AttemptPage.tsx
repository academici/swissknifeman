import { useState } from "react";
import { useParams } from "react-router";
import type { AttemptView, RunTimelineView } from "../../api/generated/execution_10";
import {
  field, record, runLink, runPath, useAttempt, useExecutionDetail, useRunEvents, useRunRead, type ReadRecord,
} from "../../api/hooks/execution";
import { withParams } from "../../api/hooks/workspace";
import { SafeLink } from "../../components/content/SafeLink";
import { EmptyState } from "../../components/data/EmptyState";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { Pagination } from "../../components/data/Pagination";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";
import { ChecksPanel } from "./ChecksPanel";
import { LiveStream } from "./LiveStream";
import { ReviewPanel, FixBriefDetails } from "./ReviewPanel";
import { StepPanel } from "./StepPanel";

function Environment({ value }: { value: unknown }) {
  const env = record(value);
  if (!Object.keys(env).length) return null;
  return <dl>
    <KeyValue label="Среда выполнения" value={field(env.kind)} />
    <KeyValue label="ID среды" value={field(env.environment_id)} />
    <KeyValue label="Состояние среды" value={field(env.state)} />
    <KeyValue label="Ветка" value={field(env.branch)} />
    {typeof env.local_locator === "string" && <KeyValue label="Локальный путь" value={env.local_locator} />}
  </dl>;
}

function Records({ title, idKey, rows }: { title: string; idKey: string; rows: readonly ReadRecord[] }) {
  return <section>
    <h2>{title}</h2>
    {rows.length ? <ul>{rows.map((row, index) => <li key={field(row[idKey], String(index))}>
      <code>{escapeText(field(row[idKey]))}</code> {escapeText(field(row.kind ?? row.source ?? row.trigger, ""))}
      {row.state != null && <> <StatusBadge status={field(row.state)} /></>}
      <JsonView value={row} />
    </li>)}</ul> : <EmptyState title="Нет записей" />}
  </section>;
}

function AttemptRecords({ runId, attempt }: { runId: string; attempt: AttemptView }) {
  const [after, setAfter] = useState<string[]>([]);
  const timeline = useRunRead<RunTimelineView>(runId, withParams("/timeline", { after_seq: after.at(-1) }));
  if (timeline.isError) return <ErrorPanel error={timeline.error} onRetry={() => { void timeline.refetch(); }} />;
  if (!timeline.data) return <Skeleton />;

  const reviewIds = new Set(attempt.reviews.map(review => review.review_id));
  const events = timeline.data.items.filter(item => {
    const payload = record(item.payload);
    const owner = item.attempt_id ?? payload.attempt_id;
    return owner == null
      ? typeof payload.review_id === "string" && reviewIds.has(payload.review_id)
      : owner === attempt.attempt_id;
  });
  return <>
    {events.length ? <ul>{events.map(item => {
      const payload = record(item.payload);
      return <li key={field(item.event_id, field(item.seq))}>
        {escapeText(field(item.code ?? item.event_type))}
        <dl>
          {payload.assignment_id != null && <KeyValue label="Назначение" value={field(payload.assignment_id)} />}
          {payload.lease_expires_at != null && <KeyValue label="Срок аренды" value={field(payload.lease_expires_at)} />}
          {payload.output_id != null && <KeyValue label="Результат" value={field(payload.output_id)} />}
          {Array.isArray(payload.new_finding_keys) && payload.new_finding_keys.length > 0 &&
            <KeyValue label="Новые ключи замечаний" value={payload.new_finding_keys.map(key => field(key)).join(", ")} />}
        </dl>
        {typeof payload.fix_brief_id === "string" && <FixBriefDetails id={payload.fix_brief_id} />}
        <JsonView value={payload} />
      </li>;
    })}</ul> : <EmptyState title="На этой странице нет событий попытки" />}
    <Pagination next={timeline.data.next_after} onNext={next => setAfter([...after, next])}
      {...(after.length ? { onPrevious: () => setAfter(after.slice(0, -1)) } : {})} />
  </>;
}

function AttemptDetail({ attemptId }: { attemptId: string }) {
  const [showRecords, setShowRecords] = useState(false);
  const attempt = useAttempt(attemptId);
  const metadata = useExecutionDetail("attempt", attemptId);
  const runId = metadata.data?.run_id ?? null;
  const projectId = metadata.data?.project_id ?? null;
  const workspaceId = metadata.data?.workspace_id ?? null;
  useRunEvents(runId, attempt.data?.eventsCursor, metadata, undefined, attemptId);
  if (attempt.isError) return <ErrorPanel error={attempt.error} onRetry={() => { void attempt.refetch(); }} />;
  if (!attempt.data) return <Skeleton />;
  const data = attempt.data.data;

  return <>
    {runId && <SafeLink href={runLink(runPath(runId), projectId)}>К запуску</SafeLink>}
    {metadata.isError && <ErrorPanel error={metadata.error} onRetry={() => void metadata.refetch()} />}
    <h2>Попытка {data.attempt_no} <StatusBadge status={data.state} /></h2>
    <dl>
      <KeyValue label="Попытка" value={data.attempt_id} id={data.attempt_id} />
      <KeyValue label="Воркер" value={field(data.worker_id)} />
      <KeyValue label="Хост" value={field(data.host_id)} />
      <KeyValue label="Начало" value={field(data.started_at, "—")} />
      <KeyValue label="Завершение" value={field(data.finished_at, "—")} />
      <KeyValue label="Причина завершения" value={field(data.end_reason, "—")} />
    </dl>
    <Environment value={record(data).environment} />
    <h2>Стадии</h2>
    {data.stages.length ? <ol>{data.stages.map((stage, index) => <li key={field(stage.stage_record_id, String(index))}>
      {escapeText(field(stage.stage_id))} · {escapeText(field(stage.stage_type))} <StatusBadge status={field(stage.state)} />
      <dl>
        <KeyValue label="Начало стадии" value={field(stage.started_at, "—")} />
        <KeyValue label="Завершение стадии" value={field(stage.finished_at, "—")} />
      </dl>
      <Environment value={stage.environment} />
      {stage.lease != null && <JsonView value={stage.lease} />}
      {data.steps.filter(step => step.stage_record_id === stage.stage_record_id).map(step =>
        <StepPanel key={field(step.step_id)} step={step} attemptId={attemptId} projectId={projectId} />)}
    </li>)}</ol> : <EmptyState title="Нет стадий" />}
    {data.steps.filter(step => !data.stages.some(stage => stage.stage_record_id === step.stage_record_id)).map(step =>
      <StepPanel key={field(step.step_id)} step={step} attemptId={attemptId} projectId={projectId} />)}
    <Records title="Результаты" idKey="output_id" rows={data.outputs} />
    <ChecksPanel checks={data.checks} />
    <ReviewPanel reviews={data.reviews} findings={data.findings} />
    <Records title="Внешние эффекты" idKey="effect_id" rows={data.effects} />
    <Records title="Восстановление" idKey="recovery_id" rows={data.recoveries} />
    <LiveStream attempt={data} projectId={projectId} workspaceId={workspaceId} />
    {runId && <details onToggle={event => setShowRecords(event.currentTarget.open)}>
      <summary>События попытки и связанные записи</summary>
      {showRecords && <AttemptRecords runId={runId} attempt={data} />}
    </details>}
  </>;
}

export default function AttemptPage() {
  const { attemptId = "" } = useParams();
  return <section><h1>Попытка</h1><AttemptDetail key={attemptId} attemptId={attemptId} /></section>;
}
