import { lazy, Suspense, useId, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router";
import { ApiError } from "../../api/errors";
import type { ExecutionDetailView } from "../../api/generated/execution-detail";
import type { RunHealth, RunTimelineView, RunView, TasksView } from "../../api/generated/execution_10";
import type { HistoryPage } from "../../api/generated/execution_06";
import {
  field, record, runLink, runPath, taskPath, useExecutionCommand, useExecutionDetail, useRun, useRunEvents, useRunRead, useRunTasks,
  type ReadRecord,
} from "../../api/hooks/execution";
import { allowed, versionTag, withParams } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { useStream } from "../../app/providers/StreamProvider";
import { SafeLink } from "../../components/content/SafeLink";
import { EmptyState } from "../../components/data/EmptyState";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { Timeline } from "../../components/data/Timeline";
import { ConflictPanel } from "../../components/feedback/ConflictPanel";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { Dialog } from "../../components/primitives/Dialog";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { Tabs } from "../../components/primitives/Tabs";
import { escapeText } from "../../lib/safeText";
import { ExportAction } from "./ExportAction";
import { BudgetPanel } from "./BudgetPanel";
import { WaitingForHuman } from "./ChecksPanel";
import { ReviewReceiptPanel } from "./ReviewPanel";
import { TaskGraph } from "./TaskGraph";

const RunLiveControl = lazy(() => import("./RunLiveControl"));

export function isHumanWait(task: ReadRecord) {
  return ["waiting", "manual_pending", "awaiting_decision"].includes(field(task.status))
    || ["WAITING_MANUAL_CHECK", "WAITING_OWNER", "WAITING_ANSWER", "WAITING_APPROVAL", "WAITING_ADVISOR"]
      .includes(field(record(task.blocking_reason).code));
}

export function BlockingReason({ value }: { value: unknown }) {
  if (value == null) return null;
  const reason = record(value);
  return <div>
    <p><code>{escapeText(field(reason.code))}</code> · {escapeText(field(reason.message))}</p>
    {reason.next_action != null && <p>Следующее действие: {escapeText(field(reason.next_action))}</p>}
    {Array.isArray(reason.allowed_actions) && reason.allowed_actions.length > 0 &&
      <p>Доступные действия: {escapeText(reason.allowed_actions.map(item => field(item)).join(", "))}</p>}
    <JsonView value={reason} />
  </div>;
}

interface Command {
  path: string;
  body: ReadRecord;
  ifMatch?: string;
}

interface Action {
  label: string;
  description?: string;
  destructive?: boolean;
  requireReason?: boolean;
  fields?: ReactNode;
  build(reason: string): Command | null;
}

export function ExecutionActionDialog({ action, onClose, onReload, onSuccess }: {
  action: Action;
  onClose(): void;
  onReload(): Promise<boolean>;
  onSuccess?(): void;
}) {
  const command = useExecutionCommand();
  const [submitted, setSubmitted] = useState<Command | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [reloading, setReloading] = useState(false);
  const active = useRef(false);
  const conflict = command.error instanceof ApiError && (command.error.isConflict() || command.error.status === 412)
    ? command.error : null;
  const canRetry = command.error instanceof ApiError && command.error.retryable;

  function submit(request: Command) {
    if (active.current) return;
    active.current = true;
    setSubmitted(request);
    command.mutate(request, {
      onSuccess: () => { onSuccess?.(); onClose(); },
      onSettled: () => { active.current = false; },
    });
  }

  async function reload() {
    setReloading(true);
    try {
      if (await onReload()) onClose();
    } finally {
      setReloading(false);
    }
  }

  return <ConfirmDialog open title={action.label} confirmLabel={action.label}
    {...(action.description === undefined ? {} : { description: action.description })}
    requireReason={action.requireReason ?? true} destructive={action.destructive ?? false}
    onClose={() => { if (!active.current) onClose(); }}
    onConfirm={reason => {
      if (conflict || active.current || reloading) return;
      const request = action.build(reason);
      setInvalid(request === null);
      if (request) submit(request);
    }}>
    {action.fields}
    {invalid && <p role="alert">Проверьте значения полей.</p>}
    {command.isPending && <p role="status">Команда отправлена…</p>}
    {command.error && !conflict && <ErrorPanel error={command.error} {...(canRetry && submitted ? {
      onRetry: () => submit(submitted),
    } : {})} />}
    {conflict && <ConflictPanel error={conflict} submitted={submitted?.body}
      current={conflict.details}
      onReload={() => { if (!reloading) void reload(); }} />}
    {reloading && <p role="status">Загрузка текущей версии…</p>}
  </ConfirmDialog>;
}

type RunAction = "pause" | "resume" | "cancel" | "reconfigure";
const labels = { pause: "Приостановить", resume: "Возобновить", cancel: "Отменить запуск", reconfigure: "Изменить лимиты" };

function Checkpoint({ state }: { state: NonNullable<ExecutionDetailView["checkpoint"]> }) {
  return <dl>
    <KeyValue label="Активная аренда" value={field(state.leased_claim)} />
    <KeyValue label="Незавершённая стадия" value={field(state.unfinished_stage)} />
    <KeyValue label="Открытое восстановление" value={field(state.open_recovery)} />
  </dl>;
}

function RunCommand({ run, etag, kind, metadata, onClose, onReload }: {
  run: RunView; etag: string | null; kind: RunAction; onClose(): void; onReload(): Promise<boolean>;
  metadata: ReturnType<typeof useExecutionDetail>;
}) {
  const id = useId();
  const [changes, setChanges] = useState<Record<string, string>>({});
  const checkpoint = metadata.data?.checkpoint;
  const blocked = checkpoint && (checkpoint.leased_claim || checkpoint.unfinished_stage || checkpoint.open_recovery);
  const options = checkpoint?.changes ?? [];
  const editable = options.filter(option => !option.locked);
  const checkpointFields = checkpoint && <>
    <Checkpoint state={checkpoint} />
    {options.length === 0 && <p>Сервер не разрешает изменять лимиты этого запуска.</p>}
    {options.filter(option => option.locked).map(option => <p key={option.key}>
      <code>{option.key}</code> · Заблокировано настройками
    </p>)}
  </>;
  if (kind === "reconfigure" && (!checkpoint || blocked || !editable.length) && Object.keys(changes).length === 0) {
    return <Dialog open title={labels[kind]} onClose={onClose}>
      <p>Версия запуска {metadata.data?.row_version ?? run.row_version}</p>
      {metadata.isError ? <ErrorPanel error={metadata.error} onRetry={() => void metadata.refetch()} /> : checkpointFields}
      {!checkpoint && !metadata.isError && (metadata.isPending ? <Skeleton /> : <p>Контрольная точка недоступна.</p>)}
      {blocked && <p>Дождитесь освобождения аренд, завершения стадий и восстановления.</p>}
      {blocked && editable.length > 0 && <p>Разрешённые изменения после контрольной точки: {editable.map(option => option.key).join(", ")}</p>}
      <Button onClick={onClose}>Закрыть</Button>
    </Dialog>;
  }
  const description = kind === "reconfigure"
    ? `Версия запуска ${run.row_version}. После применения лимитов возобновите запуск вручную.`
    : undefined;
  return <ExecutionActionDialog action={{
    label: labels[kind], destructive: kind === "cancel", requireReason: kind !== "resume",
    ...(description ? { description } : {}),
    fields: kind === "reconfigure" && <>{checkpointFields}<fieldset disabled={!checkpoint || blocked}>
      <legend>Новые лимиты. Пустые поля сохраняют текущие значения.</legend>
      {editable.map(({ key, ceiling }) => <div key={key}>
        <label htmlFor={id + key}>{key}</label>
        <input id={id + key} type="number" min={key === "execution.parallel.max_units" ? 1 : 0}
          max={ceiling > 0 ? ceiling : undefined}
          step={key.endsWith("_usd") ? "any" : 1} value={changes[key] ?? ""}
          onChange={event => setChanges({ ...changes, [key]: event.target.value })} />
        {ceiling > 0 && <small>Верхняя граница {ceiling}</small>}
      </div>)}
    </fieldset></>,
    build(reason) {
      const path = runPath(run.run_id) + "/" + kind;
      const ifMatch = etag ?? versionTag(run.row_version);
      switch (kind) {
        case "pause": return { path, body: { reason }, ifMatch };
        case "resume": return { path, body: {}, ifMatch };
        case "cancel": return { path, body: { reason } };
        case "reconfigure": {
          if (!checkpoint || blocked) return null;
          const entries = Object.entries(changes).filter(([, value]) => value !== "")
            .map(([key, value]) => [key, Number(value)] as const);
          if (!entries.length || entries.some(([key, value]) => !editable.some(option =>
            option.key === key && Number.isFinite(value) &&
            (option.ceiling === 0 || (value > 0 && value <= option.ceiling)),
          ))) return null;
          return { path, ifMatch, body: {
            reason, expected_row_version: run.row_version,
            changes: Object.fromEntries(entries),
          } };
        }
      }
    },
  }} onClose={onClose} onReload={onReload} />;
}

function TaskList({ view, runId, projectId }: { view: TasksView; runId: string; projectId: string | null }) {
  return <Table rows={view.tasks} rowKey={task => field(task.task_id)} empty="Нет задач" columns={[
    { id: "task", header: "Задача", cell: task =>
      <SafeLink href={runLink(taskPath(field(task.task_id)), projectId, runId)}>{field(task.display_key)}</SafeLink> },
    { id: "kind", header: "Тип", cell: task => escapeText(field(task.kind)) },
    { id: "status", header: "Статус", cell: task => <StatusBadge status={field(task.status)} /> },
    { id: "reason", header: "Ожидание", cell: task => <BlockingReason value={task.blocking_reason} /> },
  ]} />;
}

function History({ runId, initial }: { runId: string; initial: HistoryPage }) {
  const [after, setAfter] = useState<string[]>([]);
  const cursor = after.at(-1);
  const history = useRunRead<HistoryPage>(runId, withParams("/history", {
    through_seq: String(initial.through_seq), after: cursor,
  }), cursor !== undefined);
  const page = cursor === undefined ? initial : history.data;
  return <>
    <p>Срез истории по событие {initial.through_seq}</p>
    {cursor && history.isError ? <ErrorPanel error={history.error} onRetry={() => { void history.refetch(); }} />
      : page ? <>
        <p>Полнота: <StatusBadge status={page.coverage} /></p>
        {page.entries.length ? <ol>{page.entries.map(entry => {
          const monitor = entry.monitor_evaluation;
          const thresholds = Object.fromEntries(monitor?.thresholds.map(item => [item.key, item.value]) ?? []);
          return <li key={entry.event_id}>
            {entry.seq} · {escapeText(entry.event_type)} · <StatusBadge status={entry.coverage} />
            {monitor?.reason_code === "SOFT_DURATION_WARNING" && <p role="status">
              Мягкое предупреждение о времени: {field(thresholds["execution.timeout_enforcer.actual_seconds"] ?? thresholds.actual_seconds)}
              {" / "}{field(thresholds["execution.timeout_enforcer.expected_seconds"] ?? thresholds.expected_seconds)} с
            </p>}
            <JsonView value={entry} />
          </li>;
        })}</ol> : <EmptyState title="Нет событий истории" />}
      </> : <Skeleton />}
    <Pagination next={page?.next_after ?? null} onNext={next => setAfter([...after, next])}
      {...(after.length ? { onPrevious: () => setAfter(after.slice(0, -1)) } : {})} />
  </>;
}

function HistorySnapshot({ runId }: { runId: string }) {
  const history = useRunRead<HistoryPage>(runId, "/history");
  const [snapshot, setSnapshot] = useState<HistoryPage | null>(null);
  if (!snapshot && history.data) setSnapshot(history.data);
  if (snapshot) return <History runId={runId} initial={snapshot} />;
  if (history.isError) return <ErrorPanel error={history.error} onRetry={() => { void history.refetch(); }} />;
  return <Skeleton />;
}

function RunTimeline({ runId }: { runId: string }) {
  const [after, setAfter] = useState<string[]>([]);
  const [history, setHistory] = useState(false);
  const timeline = useRunRead<RunTimelineView>(runId, withParams("/timeline", { after_seq: after.at(-1) }));
  return <>
    <h2>Хронология</h2>
    {timeline.isError ? <ErrorPanel error={timeline.error} onRetry={() => { void timeline.refetch(); }} />
      : timeline.data ? <>
        {timeline.data.items.length ? <Timeline events={timeline.data.items.map(item => ({
          id: field(item.event_id, field(item.seq)), time: field(item.at), type: field(item.code ?? item.event_type),
          detail: field(item.summary), ...(typeof item.task_id === "string" ? { task: item.task_id } : {}),
        }))} /> : <EmptyState title="Нет событий" />}
        <Pagination next={timeline.data.next_after} onNext={next => setAfter([...after, next])}
          {...(after.length ? { onPrevious: () => setAfter(after.slice(0, -1)) } : {})} />
      </> : <Skeleton />}
    <details onToggle={event => setHistory(event.currentTarget.open)}>
      <summary>Причинная история</summary>
      {history && <HistorySnapshot runId={runId} />}
    </details>
  </>;
}

function Health({ run }: { run: RunView }) {
  const health = useRunRead<RunHealth>(run.run_id, "/health");
  const view = health.data ?? run.health;
  return <>
    <h2>Состояние запуска</h2>
    <StatusBadge status={field(view.health)} />
    {health.isError && <ErrorPanel error={health.error} onRetry={() => { void health.refetch(); }} />}
    {Array.isArray(view.reasons) && <ul>{view.reasons.map((reason: unknown, index) =>
      <li key={index}>{escapeText(field(reason))}</li>)}</ul>}
  </>;
}

function RunDetail({ runId }: { runId: string }) {
  const { stale } = useStream();
  const { me } = useAuth();
  const detail = useRun(runId);
  const tasks = useRunTasks(runId, detail.isSuccess);
  const metadata = useExecutionDetail("run", runId);
  const origin = metadata.data;
  const [tab, setTab] = useState("graph");
  const [action, setAction] = useState<{ kind: RunAction; run: RunView; etag: string | null } | null>(null);
  useRunEvents(runId, detail.data?.eventsCursor, metadata);
  if (detail.isError && !detail.data) return <ErrorPanel error={detail.error} onRetry={() => { void detail.refetch(); }} />;
  if (!detail.data) return <Skeleton />;

  const { data: run, etag } = detail.data;
  const projectId = origin?.project_id ?? null;
  const workspaceId = origin?.workspace_id ?? null;
  const hasControl = origin && allowed(me, "run.control", runId, run.plan_id, projectId, workspaceId);
  const available: RunAction[] = [];
  if (hasControl) {
    if (["running", "waiting"].includes(run.status)) available.push("pause");
    if (run.status === "paused") available.push("resume", "reconfigure");
    if (["running", "waiting", "paused", "created", "ready"].includes(run.status)) available.push("cancel");
  }
  const taskView = (render: (view: TasksView) => ReactNode) => tasks.isError
    ? <ErrorPanel error={tasks.error} onRetry={() => { void tasks.refetch(); }} />
    : tasks.data ? render(tasks.data) : <Skeleton />;
  const waiting = tasks.data?.tasks.filter(isHumanWait) ?? [];

  return <>
    {stale && <p role="status">Данные могут быть устаревшими.</p>}
    <h2>{run.revision_no === null ? "Разовый запуск" : `${escapeText(run.plan_alias)} · r${run.revision_no}`} <StatusBadge status={run.status} /></h2>
    {origin && me?.modules.exports && allowed(me, "run.read", runId, run.plan_id, projectId, workspaceId) &&
      <ExportAction key={runId} runId={runId} />}
    {metadata.isError && <ErrorPanel error={metadata.error} onRetry={() => void metadata.refetch()} />}
    <dl>
      <KeyValue label="Тип" value={run.kind} />
      <KeyValue label="Запуск" value={run.run_id} id={run.run_id} />
      {origin?.revision_id && <KeyValue label="Ревизия" value={origin.revision_id} id={origin.revision_id} />}
      <KeyValue label="Дайджест пакета" value={field(run.bundle_digest)} />
      {origin?.workflow && <>
        <KeyValue label="Зафиксированный workflow" value={`${field(origin.workflow.key)} @ ${field(origin.workflow.version)}`} />
        <KeyValue label="Версия ресурса workflow" value={origin.workflow.resource_version_id} id={origin.workflow.resource_version_id} />
        <KeyValue label="Дайджест workflow" value={field(origin.workflow.digest)} />
      </>}
      <KeyValue label="Группировка ревью" value={run.review_grouping} />
      <KeyValue label="Начало" value={field(run.started_at, "—")} />
      <KeyValue label="Завершение" value={field(run.finished_at, "—")} />
      {run.stop_code && <KeyValue label="Код остановки" value={run.stop_code} />}
      {run.pause_source && <KeyValue label="Источник паузы" value={run.pause_source} />}
    </dl>
    {run.selection && <details><summary>Выбор задач запуска</summary><JsonView value={run.selection} /></details>}
    {Object.keys(run.counts_by_status).length > 0 && <ul aria-label="Задачи по статусам">
      {Object.entries(run.counts_by_status).map(([status, count]) =>
        <li key={status}><StatusBadge status={status} /> {escapeText(field(count))}</li>)}
    </ul>}
    {available.length > 0 && <div className="confirm-actions">
      {available.map(kind => <Button key={kind} onClick={() => {
        if (kind === "reconfigure") void metadata.refetch();
        setAction({ kind, run, etag });
      }}>{labels[kind]}</Button>)}
    </div>}
    {action && <RunCommand {...action} metadata={metadata} onClose={() => setAction(null)}
      onReload={async () => (await Promise.all([detail.refetch(), metadata.refetch()])).every(result => result.isSuccess)} />}
    {(run.status === "waiting" || run.stop_code === "WAITING_MANUAL_CHECK" || waiting.length > 0) && <WaitingForHuman />}
    {waiting.map(task => <div key={field(task.task_id)}>
      <SafeLink href={runLink(taskPath(field(task.task_id)), projectId, runId)}>{field(task.display_key)}</SafeLink>
      <BlockingReason value={task.blocking_reason} />
    </div>)}
    {run.kind === "review_request" && <ReviewReceiptPanel runId={runId} />}
    <Tabs label="Запуск" active={tab} onSelect={setTab} tabs={[
      { id: "graph", label: "Граф", content: taskView(view => <TaskGraph view={view} projectId={projectId} runId={runId} />) },
      { id: "tasks", label: "Задачи", content: taskView(view => <TaskList view={view} projectId={projectId} runId={runId} />) },
      { id: "timeline", label: "Хронология", content: tab === "timeline" && <RunTimeline runId={runId} /> },
      { id: "budget", label: "Бюджет", content: tab === "budget" && <BudgetPanel run={run} projectId={projectId} /> },
      { id: "live-control", label: "Управление и инструменты", content: tab === "live-control" && taskView(view =>
        <Suspense fallback={<Skeleton />}><RunLiveControl runId={runId} tasks={view.tasks}
          canControl={Boolean(hasControl) && ["running", "waiting", "paused", "ready", "created"].includes(run.status)} /></Suspense>) },
      { id: "health", label: "Состояние", content: tab === "health" && <Health run={run} /> },
    ]} />
  </>;
}

export default function RunPage() {
  const { runId = "" } = useParams();
  return <section><h1>Запуск</h1><RunDetail key={runId} runId={runId} /></section>;
}
