import { useId, useState } from "react";
import { useParams } from "react-router";
import type { TaskView } from "../../api/generated/execution_10";
import { attemptPath, field, record, runLink, runPath, taskPath, useExecutionDetail, useRunEvents, useTask, useTaskAttempts } from "../../api/hooks/execution";
import { allowed } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { SafeLink } from "../../components/content/SafeLink";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";
import { WorkPolicy } from "./BudgetPanel";
import { WaitingForHuman } from "./ChecksPanel";
import { BlockingReason, ExecutionActionDialog, isHumanWait } from "./RunPage";

type TaskAction = "restart" | "skip" | "carry-forward";
const labels = { restart: "Перезапустить задачу", skip: "Пропустить задачу", "carry-forward": "Перенести результат" };

function TaskCommand({ kind, task, requiresOverride, onClose, onReload }: {
  kind: TaskAction; task: TaskView; requiresOverride: boolean; onClose(): void; onReload(): Promise<boolean>;
}) {
  const id = useId();
  const [source, setSource] = useState("");
  const [decision, setDecision] = useState("");
  const [raiseAttempts, setRaiseAttempts] = useState(false);
  return <ExecutionActionDialog action={{
    label: labels[kind], destructive: kind === "skip",
    fields: kind === "carry-forward" ? <>
      <label htmlFor={id}>ID исходной задачи</label>
      <input id={id} value={source} required onChange={event => setSource(event.target.value)} />
    </> : kind === "skip" ? <>
      <label htmlFor={id}>Ссылка на решение</label>
      <input id={id} value={decision} onChange={event => setDecision(event.target.value)} />
    </> : requiresOverride && <label>
      <input type="checkbox" required checked={raiseAttempts} onChange={event => setRaiseAttempts(event.target.checked)} />
      Поднять лимит попыток
    </label>,
    build(reason) {
      const path = taskPath(task.task_id) + "/" + kind;
      if (kind === "carry-forward") return source.trim() ? { path, body: { reason, source_task_id: source.trim() } } : null;
      if (kind === "skip") return { path, body: { reason, ...(decision.trim() ? { decision_ref: decision.trim() } : {}) } };
      if (requiresOverride && !raiseAttempts) return null;
      return { path, body: { reason, ...(requiresOverride ? { raise_attempts_limit: true } : {}) } };
    },
  }} onClose={onClose} onReload={onReload} />;
}

function TaskDetail({ taskId }: { taskId: string }) {
  const { me } = useAuth();
  const task = useTask(taskId);
  const metadata = useExecutionDetail("task", taskId);
  const origin = metadata.data;
  const runId = origin?.run_id ?? null;
  const attempts = useTaskAttempts(taskId);
  const [action, setAction] = useState<TaskAction | null>(null);
  useRunEvents(runId, task.data?.eventsCursor, metadata, taskId);
  if (task.isError) return <ErrorPanel error={task.error} onRetry={() => { void task.refetch(); }} />;
  if (!task.data) return <Skeleton />;
  const data = task.data.data;
  const projectId = origin?.project_id ?? null;
  const mayControl = origin && allowed(me, "run.control", runId, origin.plan_id, projectId, origin.workspace_id);
  const mayCarry = origin && allowed(me, "deviation.accept", runId, origin.plan_id, projectId, origin.workspace_id);
  const mayOverrideAttempts = me?.principal.kind === "human" && mayCarry;
  const requiresOverride = origin?.restart?.requires_attempts_override === true;
  const mayRestart = mayControl && origin.restart?.eligible && (!requiresOverride || mayOverrideAttempts);
  const reason = record(data.blocking_reason);
  const actions = Array.isArray(reason.allowed_actions) ? reason.allowed_actions : [];
  const links = (ids: readonly string[]) => <ul>{ids.map(id => <li key={id}>
    <SafeLink href={runLink(taskPath(id), projectId, runId)}>{id}</SafeLink>
  </li>)}</ul>;

  return <>
    {runId && <SafeLink href={runLink(runPath(runId), projectId)}>К запуску</SafeLink>}
    {metadata.isError && <ErrorPanel error={metadata.error} onRetry={() => void metadata.refetch()} />}
    <h2>{escapeText(data.display_key)} <StatusBadge status={data.status} /></h2>
    {isHumanWait(record(data)) && <WaitingForHuman />}
    <BlockingReason value={data.blocking_reason} />
    <dl>
      <KeyValue label="Задача" value={data.task_id} id={data.task_id} />
      <KeyValue label="Тип" value={data.kind} />
      <KeyValue label="Режим ревью" value={data.review_mode} />
      <KeyValue label="Профиль ревью" value={field(data.review_profile)} />
      <KeyValue label="Раунды исправления проверок" value={data.check_fix_rounds} />
      <KeyValue label="Раунды ревью" value={data.review_rounds} />
      <KeyValue label="Принятый результат" value={field(data.accepted_output_id, "—")} />
    </dl>
    <div className="confirm-actions">
      {mayRestart &&
        <Button onClick={() => setAction("restart")}>{labels.restart}</Button>}
      {mayControl && (["blocked", "ready", "awaiting_decision"].includes(data.status) || actions.includes("skip_task")) &&
        <Button onClick={() => setAction("skip")}>{labels.skip}</Button>}
      {mayCarry && ["assigned", "executing"].includes(data.status) &&
        <Button onClick={() => setAction("carry-forward")}>{labels["carry-forward"]}</Button>}
    </div>
    {action && (action !== "restart" || mayRestart) &&
      <TaskCommand kind={action} task={data} requiresOverride={requiresOverride} onClose={() => setAction(null)}
        onReload={async () => (await Promise.all([task.refetch(), metadata.refetch()])).every(result => result.isSuccess)} />}
    {Boolean(data.gate_members?.length) && <><h3>Задачи контрольной точки</h3>{links(data.gate_members ?? [])}</>}
    {Boolean(data.followups?.length) && <><h3>Последующие задачи</h3>{links(data.followups ?? [])}</>}
    <h2>Попытки</h2>
    {attempts.isError ? <ErrorPanel error={attempts.error} onRetry={() => { void attempts.refetch(); }} />
      : <Table rows={attempts.data?.attempts ?? data.attempts} rowKey={attempt => field(attempt.attempt_id)} empty="Нет попыток" columns={[
        { id: "attempt", header: "Попытка", cell: attempt => <SafeLink
          href={runLink(attemptPath(field(attempt.attempt_id)), projectId, runId)}>
          {`Попытка ${field(attempt.attempt_no)}`}
        </SafeLink> },
        { id: "state", header: "Статус", cell: attempt => <StatusBadge status={field(attempt.state)} /> },
        { id: "worker", header: "Воркер", cell: attempt => escapeText(field(attempt.worker_id)) },
        { id: "host", header: "Хост", cell: attempt => escapeText(field(attempt.host_id)) },
        { id: "started", header: "Начало", cell: attempt => escapeText(field(attempt.started_at, "—")) },
        { id: "ended", header: "Завершение", cell: attempt => escapeText(field(attempt.finished_at, "—")) },
        { id: "reason", header: "Причина завершения", cell: attempt => escapeText(field(attempt.end_reason, "—")) },
        { id: "outputs", header: "Результаты", cell: attempt => <JsonView value={attempt.outputs ?? []} /> },
      ]} />}
    <h2>Зафиксированная политика интенсивности задачи</h2>
    <WorkPolicy policy={data.work_policy} />
  </>;
}

export default function TaskPage() {
  const { taskId = "" } = useParams();
  return <section><h1>Задача</h1><TaskDetail key={taskId} taskId={taskId} /></section>;
}
