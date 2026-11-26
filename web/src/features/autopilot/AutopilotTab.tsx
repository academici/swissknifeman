import { useState } from "react";
import { useParams } from "react-router";
import { ApiError } from "../../api/errors";
import type { AutopilotExplainView, AutopilotStatusView } from "../../api/generated/execution_10";
import type { Uuid } from "../../api/generated/kernel";
import {
  field, runLink, runPath, useAutopilot, useAutopilotCommand, useAutopilotEntry, type AutopilotAction,
} from "../../api/hooks/execution";
import { useSettingsPermissions } from "../../api/hooks/settings";
import { SafeLink } from "../../components/content/SafeLink";
import { DataList } from "../../components/data/DataList";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";

function Status({ view, projectId }: { view: AutopilotStatusView; projectId: string }) {
  return <>
    <h2>Состояние автопилота</h2>
    <DataList>
      <KeyValue label="Эффективное состояние" value={<StatusBadge status={view.effective_state} />} />
      <KeyValue label="Состояние сессии" value={view.state} />
      <KeyValue label="Экстренная остановка" value={field(view.emergency)} />
      <KeyValue label="Начало сессии" value={view.session_started_at ?? "—"} />
      <KeyValue label="Текущий запуск" value={view.current_run_id
        ? <SafeLink href={runLink(runPath(view.current_run_id), projectId)}>{view.current_run_id}</SafeLink> : "—"} />
      <KeyValue label="Код остановки" value={view.stop_code ?? "—"} />
      <KeyValue label="Причина остановки" value={view.stop_detail ?? "—"} />
    </DataList>
    <h2>Счётчики сессии</h2>
    <DataList>{Object.entries(view.counters).map(([name, value]) =>
      <KeyValue key={name} label={name} value={field(value)} />)}</DataList>
    <h2>Очередь</h2>
    {view.queue.length === 0 ? <p>Очередь пуста.</p> : <ol>{view.queue.map((row, index) => <li key={index}>
      {escapeText(field(row.alias ?? row.ref ?? row.plan_id))} <StatusBadge status={field(row.status)} />
      <JsonView value={row} />
    </li>)}</ol>}
  </>;
}

function Explanation({ view }: { view: AutopilotExplainView }) {
  return <section>
    <h2>Объяснение</h2>
    <JsonView value={view.status} />
    <h3>Настройки и их источники</h3>
    <DataList>{view.keys.map(row => <KeyValue key={field(row.key)} label={field(row.key)}
      value={<>{escapeText(JSON.stringify(row.value) ?? "—")} <JsonView value={row.provenance} /></>} />)}</DataList>
    <h3>Условия остановки</h3>
    <ol>{view.stop_conditions.map((row, index) => <li key={index}>
      {escapeText(field(row.id, ""))} {escapeText(field(row.code, ""))} <JsonView value={row} />
    </li>)}</ol>
    {view.next_plan && <><h3>Следующий план</h3>
      <p>{escapeText(field(view.next_plan.alias ?? view.next_plan.ref ?? view.next_plan.plan_id))}</p>
      <JsonView value={view.next_plan} /></>}
  </section>;
}

const labels = {
  enable: "Включить", disable: "Выключить", start: "Запустить", newSession: "Новая сессия",
  pause: "Приостановить", drain: "Завершить после текущего запуска", stop: "Остановить",
  emergency: "Экстренная остановка",
};
type Action = keyof typeof labels;

function Controls({ projectId, status, explain }: {
  projectId: string; status: AutopilotStatusView | undefined; explain: AutopilotExplainView | undefined;
}) {
  const permissions = useSettingsPermissions({ level: "project", scope_id: projectId as Uuid });
  const canConfigure = permissions.has("config.write");
  const canControl = permissions.has("run.control");
  const entry = useAutopilotEntry(projectId, canConfigure);
  const mutation = useAutopilotCommand(projectId);
  const [action, setAction] = useState<Action | null>(null);
  const [last, setLast] = useState<{ action: Action; label: string; reason: string } | null>(null);
  const [retrying, setRetrying] = useState(false);
  const may = (value: Action) => value === "enable" || value === "disable" ? canConfigure : canControl;
  const label = (value: Action) => value === "start" && (status?.state === "paused" || status?.state === "stopped")
    ? "Продолжить" : labels[value];
  const enabled = explain?.keys.find(row => row.key === "execution.autopilot.enabled")?.value;

  function confirm(reason: string) {
    if (!status || !action || !may(action) || mutation.status === "pending") return;
    let command: AutopilotAction;
    switch (action) {
      case "enable": case "disable": {
        if (!entry.data || entry.isError || typeof enabled !== "boolean" || enabled === (action === "enable")) return;
        const row = entry.data.items.find(item => item.key === "execution.autopilot.enabled");
        command = { action: "configure", value: action === "enable", version: row?.row_version ?? null, reason };
        break;
      }
      case "start": case "newSession":
        command = { action: "start", body: { reason, new_session: action === "newSession" } }; break;
      case "emergency": case "stop":
        command = { action: "stop", body: { reason, emergency: action === "emergency" } }; break;
      default: command = { action, body: { reason } };
    }
    setLast({ action, label: label(action), reason });
    setAction(null);
    mutation.submit(command);
  }

  const actions: Action[] = [];
  if (canConfigure && typeof enabled === "boolean") actions.push(enabled ? "disable" : "enable");
  if (canControl) actions.push("start", "newSession", "pause", "drain", "stop", "emergency");
  const retryable = mutation.error instanceof ApiError && (mutation.error.status === 0 || mutation.error.retryable);
  return <>
    {status && actions.map(value => <Button key={value}
      disabled={mutation.status === "pending" || ((value === "enable" || value === "disable") && (!entry.data || entry.isError))}
      onClick={() => setAction(value)}>{label(value)}</Button>)}
    {canConfigure && entry.isError && <ErrorPanel error={entry.error} onRetry={() => void entry.refetch()} />}
    {action && may(action) && <ConfirmDialog open title={label(action)} requireReason
      destructive={action === "emergency"} onClose={() => setAction(null)} onConfirm={confirm}
      description={action === "emergency" ? "Все активные запуски проекта будут отменены."
        : action === "newSession" ? "Счётчики и время начала сессии будут сброшены." : ""} />}
    {mutation.error && <ErrorPanel error={mutation.error}
      {...(retryable && last && may(last.action) ? { onRetry: () => setRetrying(true) } : {})} />}
    {retrying && last && may(last.action) && <ConfirmDialog open title={last.label}
      description={last.reason} confirmLabel="Повторить запрос" destructive={last.action === "emergency"}
      onClose={() => setRetrying(false)} onConfirm={() => { setRetrying(false); mutation.retry(); }} />}
  </>;
}

function ProjectAutopilot({ projectId }: { projectId: string }) {
  const { status, explain } = useAutopilot(projectId);
  return <>
    {status.data ? <Status view={status.data} projectId={projectId} /> : status.isPending && <Skeleton />}
    {status.isError && <ErrorPanel error={status.error} onRetry={() => void status.refetch()} />}
    <Controls projectId={projectId} status={status.isError ? undefined : status.data}
      explain={explain.isError ? undefined : explain.data} />
    {explain.isError ? <ErrorPanel error={explain.error} onRetry={() => void explain.refetch()} />
      : explain.data ? <Explanation view={explain.data} /> : <Skeleton />}
  </>;
}

export default function AutopilotTab() {
  const { projectId = "" } = useParams();
  return <section><h1>Автопилот</h1><ProjectAutopilot key={projectId} projectId={projectId} /></section>;
}
