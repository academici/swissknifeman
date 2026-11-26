import type { RunView } from "../../api/generated/execution_10";
import { field, record, runLink, taskPath, useRunBudget, type ReadRecord } from "../../api/hooks/execution";
import { SafeLink } from "../../components/content/SafeLink";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Skeleton } from "../../components/primitives/Skeleton";
import { escapeText } from "../../lib/safeText";

export function WorkPolicy({ policy }: { policy: unknown }) {
  if (policy == null) return <p>Интенсивность неизвестна</p>;
  const snapshot = record(policy);
  const requested = record(snapshot.requested);
  const effective = record(snapshot.effective);
  const roles = record(effective.role_intensity);
  const warnings = record(snapshot.role_warn_seconds);
  const limits = record(snapshot.emergency_role_seconds);
  return <>
    <Table rows={Object.keys(roles)} rowKey={role => role} columns={[
      { id: "role", header: "Роль", cell: role => escapeText(role) },
      { id: "requested", header: "Запрошено", cell: role => escapeText(field(record(requested.role_intensity)[role])) },
      { id: "effective", header: "Применено", cell: role => escapeText(field(roles[role])) },
      { id: "warning", header: "Мягкий порог, с", cell: role => escapeText(field(warnings[role])) },
      { id: "emergency", header: "Аварийный предел, с", cell: role =>
        limits[role] === null ? "Без предела" : escapeText(field(limits[role])) },
    ]} />
    <dl>
      <KeyValue label="Интенсивность проверки" value={`${field(requested.verification_intensity)} → ${field(effective.verification_intensity)}`} />
      <KeyValue label="Мягкий порог воспроизведения при триаже, с" value={field(snapshot.triage_repro_warn_seconds)} />
    </dl>
    <JsonView value={snapshot} />
  </>;
}

function softTokenThreshold(value: unknown) {
  return value === 0 ? "Отключён" : field(value);
}

export function TokenBudgetPreview({ value }: { value: unknown }) {
  const budget = record(value);
  return <dl>
    <KeyValue label="Мягкий порог токенов на задачу" value={softTokenThreshold(budget.task_warn_tokens)} />
    <KeyValue label="Жёсткий лимит токенов на задачу" value={budget.task_max_tokens === 0 ? "Без лимита" : field(budget.task_max_tokens)} />
    <KeyValue label="Жёсткий лимит токенов на запуск" value={budget.run_max_tokens === 0 ? "Без лимита" : field(budget.run_max_tokens)} />
  </dl>;
}

function SoftTokenWarning({ account }: { account: ReadRecord }) {
  if (account.dimension !== "tokens" || account.scope !== "task") return "—";
  const overrun = record(account.soft_overrun);
  return <>
    {escapeText(softTokenThreshold(account.warn_tokens))}
    {account.actual_tokens === null && <p>Фактический расход токенов неизвестен.</p>}
    {overrun.measured_tokens != null && <p role="status">
      Мягкое предупреждение о токенах: {overrun.partial === true ? "не менее " : ""}
      {field(overrun.measured_tokens)} / {field(overrun.expected_tokens)} токенов
    </p>}
  </>;
}

export function BudgetPanel({ run, projectId }: { run: RunView; projectId: string | null }) {
  const budget = useRunBudget(run.run_id);
  return <>
    <h2>Бюджет</h2>
    {run.unmetered && <p role="status">Учёт расхода неполный (unmetered)</p>}
    {budget.isError ? <ErrorPanel error={budget.error} onRetry={() => { void budget.refetch(); }} />
      : budget.data ? <>
        <p>Шаги с неизвестным расходом: {budget.data.unknown_usage_steps}</p>
        <Table rows={budget.data.accounts} rowKey={(account) => field(account.account_id,
          `${field(account.scope)}:${field(account.task_id)}:${field(account.dimension)}`)} columns={[
          { id: "scope", header: "Область", cell: account => typeof account.task_id === "string"
            ? <SafeLink href={runLink(taskPath(account.task_id), projectId, run.run_id)}>{account.task_id}</SafeLink>
            : escapeText(field(account.scope)) },
          { id: "dimension", header: "Единица", cell: account => escapeText(field(account.dimension)) },
          { id: "warn", header: "Мягкий порог токенов", cell: account => <SoftTokenWarning account={account} /> },
          { id: "limit", header: "Жёсткий лимит", cell: account => account.limit === null ? "Без лимита" : escapeText(field(account.limit)) },
          { id: "spent", header: "Израсходовано", cell: account => {
            const ratio = Number(account.spent) / Number(account.limit);
            return <>{escapeText(field(account.spent))}{account.limit != null && Number.isFinite(ratio) && ratio >= 0.8 &&
              <p role="status">{ratio >= 1 ? "Лимит достигнут" : "Лимит близок"} · {Math.floor(ratio * 100)}%</p>}</>;
          } },
          { id: "reserved", header: "Зарезервировано", cell: account => escapeText(field(account.reserved)) },
          { id: "remaining", header: "Остаток", cell: account => account.limit === null ? "Без лимита" : escapeText(field(account.remaining)) },
        ]} />
      </> : <Skeleton />}
    <h3>Зафиксированная политика интенсивности запуска</h3>
    <WorkPolicy policy={run.work_policy_default} />
    <p>При превышении мягкого порога работа может продолжаться.</p>
  </>;
}
