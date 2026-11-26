import { useId, useState } from "react";
import type { TaskLiveControlView } from "../../api/generated/execution-live-control";
import type { TasksView } from "../../api/generated/execution_10";
import { field, useRunRead } from "../../api/hooks/execution";
import { segment, versionTag, withParams } from "../../api/hooks/workspace";
import { EmptyState } from "../../components/data/EmptyState";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { escapeText } from "../../lib/safeText";
import { ExecutionActionDialog } from "./RunPage";

const actions = {
  reroute_task: { path: "reroute", label: "Изменить маршрут", fields: [["runtime_id", "Среда выполнения"], ["model", "Модель"]] },
  override_actor: { path: "override-actor", label: "Заменить профиль агента", fields: [["actor_profile", "Ключ профиля"]] },
  steer_task: { path: "steer", label: "Добавить инструкции", fields: [["instructions", "Инструкции"]] },
  abort_step: { path: "abort-step", label: "Прервать шаг", fields: [] },
} as const;
type ActionKind = keyof typeof actions;

const coverageLabel = { complete: "Полное", partial: "Частичное", unavailable: "Недоступно" };

function LiveCommand({ kind, base, snapshot, onClose, onReload }: {
  kind: ActionKind;
  base: string;
  snapshot: TaskLiveControlView;
  onClose(): void;
  onReload(): Promise<boolean>;
}) {
  const id = useId();
  const [fields, setFields] = useState<Record<string, string>>({});
  const { label, path, fields: required } = actions[kind];
  return <ExecutionActionDialog onClose={onClose} onReload={onReload} action={{
    label,
    destructive: kind === "abort_step",
    description: kind === "abort_step" ? "Сервер запросит остановку и проверит завершение процесса."
      : "Изменение вступит в силу при подготовке следующего шага агента.",
    fields: required.map(([name, title]) => <label key={name} htmlFor={id + name}>
      {title}
      {name === "instructions" ?
        <textarea id={id + name} maxLength={2000} value={fields[name] ?? ""}
          onChange={event => setFields({ ...fields, [name]: event.target.value })} /> :
        <input id={id + name} maxLength={name === "runtime_id" ? 100 : name === "actor_profile" ? 180 : 200}
          value={fields[name] ?? ""} onChange={event => setFields({ ...fields, [name]: event.target.value })} />}
    </label>),
    build: reason => required.some(([name]) => !fields[name]?.trim()) ? null : {
      path: base + "/" + path,
      ifMatch: versionTag(snapshot.row_version),
      body: {
        ...Object.fromEntries(required.map(([name]) => [name, fields[name]?.trim()])),
        expected_assignment_id: snapshot.assignment_id,
        expected_fencing_token: snapshot.fencing_token,
        expected_step_id: snapshot.active_step_id,
        reason,
      },
    },
  }} />;
}

function TaskLiveControl({ runId, taskId, canControl }: { runId: string; taskId: string; canControl: boolean }) {
  const [stepId, setStepId] = useState("");
  const [pages, setPages] = useState<string[]>([]);
  const [command, setCommand] = useState<{ kind: ActionKind; snapshot: TaskLiveControlView } | null>(null);
  const path = "/tasks/" + segment(taskId);
  const live = useRunRead<TaskLiveControlView>(
    runId, withParams(path + "/live-control", { step_id: stepId, after_call_id: pages.at(-1) }), true, true,
  );
  if (live.isError && !live.data) return <ErrorPanel error={live.error} onRetry={() => void live.refetch()} />;
  if (!live.data) return <Skeleton />;

  const view = live.data;
  const selected = view.steps.find(step => step.step_id === view.selected_step_id);
  const controlButtons: ActionKind[] = ["reroute_task", "override_actor", "steer_task"];
  if (view.active_step_id && !view.cancellation_requested) controlButtons.push("abort_step");
  return <>
    <Button onClick={() => void live.refetch()} disabled={live.isFetching}>Обновить управление и вызовы</Button>
    {live.isError && <ErrorPanel error={live.error} />}
    {canControl && <div className="confirm-actions">
      {controlButtons.map(kind => <Button key={kind} onClick={() => setCommand({ kind, snapshot: view })}>
        {actions[kind].label}
      </Button>)}
    </div>}
    {command && <LiveCommand {...command} base={"/runs/" + segment(runId) + path}
      onClose={() => setCommand(null)} onReload={async () => (await live.refetch()).isSuccess} />}
    {view.cancellation_requested && <p role="status">Запрошена остановка шага.</p>}
    {view.pending_controls.length > 0 && <p role="status">
      К следующему шагу: {view.pending_controls.map(kind => actions[kind].label).join(", ")}
    </p>}
    <h3>Вызовы инструментов</h3>
    {view.steps.length === 0 ? <EmptyState title="У задачи пока нет шагов" /> : <>
      <label>Шаг <select value={view.selected_step_id ?? ""} onChange={event => {
        setStepId(event.target.value);
        setPages([]);
      }}>
        {view.steps.map(step => <option key={step.step_id} value={step.step_id}>
          {escapeText(step.role)} · {escapeText(step.state)} · {escapeText(step.step_id)}
        </option>)}
      </select></label>
      <p>Покрытие наблюдений: {coverageLabel[selected?.coverage === "unavailable" && view.tool_calls.length
        ? "partial" : selected?.coverage ?? "unavailable"]}</p>
      {view.tool_calls.length === 0 ? <EmptyState title="Нет зарегистрированных вызовов" /> :
        <Table rows={view.tool_calls} rowKey={call => call.call_id} columns={[
          { id: "call", header: "Идентификатор", cell: call => escapeText(call.call_id) },
          { id: "tool", header: "Инструмент", cell: call => escapeText(call.tool ?? "Неизвестно") },
          { id: "duration", header: "Длительность, мс", cell: call => call.duration_ms ?? "Неизвестно" },
        ]} />}
      <Pagination next={view.next_call_id} busy={live.isFetching}
        {...(pages.length > 0 && { onPrevious: () => setPages(pages.slice(0, -1)) })}
        onNext={cursor => {
          setStepId(view.selected_step_id ?? "");
          setPages([...pages, cursor]);
        }} />
    </>}
  </>;
}

const closedTasks = new Set(["accepted", "skipped", "failed", "cancelled", "superseded"]);

export default function RunLiveControl({ runId, tasks, canControl }: {
  runId: string;
  tasks: TasksView["tasks"];
  canControl: boolean;
}) {
  const [selected, setSelected] = useState("");
  const choices = tasks.flatMap(item => typeof item.task_id === "string" ? [{
    id: item.task_id, label: field(item.display_key, item.task_id), closed: closedTasks.has(field(item.status)),
  }] : []);
  const task = choices.find(item => item.id === selected) ?? choices.find(item => !item.closed) ?? choices[0];
  if (!task) return <EmptyState title="Нет задач" />;
  return <>
    <label>Задача <select value={task.id} onChange={event => setSelected(event.target.value)}>
      {choices.map(item => <option key={item.id} value={item.id}>{escapeText(item.label)}</option>)}
    </select></label>
    <TaskLiveControl key={task.id} runId={runId} taskId={task.id}
      canControl={canControl && !task.closed} />
  </>;
}
