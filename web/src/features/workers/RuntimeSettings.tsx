import { Link } from "react-router";
import { useRuntimeSettings } from "../../api/hooks/runtimes";
import { allowed, operatorError } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { JsonView } from "../../components/data/JsonView";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Skeleton } from "../../components/primitives/Skeleton";
import { escapeText } from "../../lib/safeText";

const hostValues = ["runtimes.host.enabled_runtimes", "runtimes.host.enabled_models", "runtimes.host.route_substitutions"];
const budgetValues = [
  ["budgets.run.max_usd", "Стоимость запуска (USD)"],
  ["budgets.run.max_tokens", "Токены запуска"],
  ["budgets.task.max_usd", "Стоимость задачи (USD)"],
  ["budgets.task.max_tokens", "Токены задачи"],
] as const;

function route(value: unknown) {
  if (typeof value !== "object" || value === null ||
      !("runtime_id" in value) || !("model_id" in value) || !("effort" in value)) return null;
  const { runtime_id, model_id, effort } = value;
  if (typeof runtime_id !== "string" || typeof model_id !== "string" || typeof effort !== "string") return null;
  return escapeText(`${runtime_id} / ${model_id} / ${effort}`);
}

export function HostRoutingSettings({ host }: { host: string }) {
  const scope = `host:${host}`;
  const query = useRuntimeSettings(scope, hostValues);
  const value = (name: string) => query.data?.keys.find(row => row.key === name && row.sensitivity === "public")?.value;
  const raw = value("runtimes.host.route_substitutions");
  const substitutions = (Array.isArray(raw) ? raw : []).flatMap((entry: unknown, index) => {
    if (typeof entry !== "object" || entry === null || !("requested" in entry) || !("selected" in entry)) return [];
    const requested = route(entry.requested);
    const selected = route(entry.selected);
    return requested && selected ? [{ requested, selected, index }] : [];
  });
  return <section>
    <h3>Подстановки маршрутов хоста</h3>
    <Link to={`/settings?${new URLSearchParams({ scope })}`}>Настройки хоста</Link>
    {query.isError ? <ErrorPanel error={operatorError(query.error)} onRetry={() => void query.refetch()} />
      : query.isPending ? <Skeleton /> : <>
        <Table rows={substitutions} rowKey={entry => entry.index} empty="Нет подстановок" columns={[
          { id: "requested", header: "Запрошенный маршрут", cell: entry => entry.requested },
          { id: "selected", header: "Маршрут замены", cell: entry => entry.selected },
        ]} />
        <h4>Разрешённые среды и модели хоста</h4>
        <JsonView value={{
          enabled_runtimes: value("runtimes.host.enabled_runtimes"),
          enabled_models: value("runtimes.host.enabled_models"),
        }} />
      </>}
  </section>;
}

function ExecutionBudgets({ scope }: { scope: string }) {
  const query = useRuntimeSettings(scope, budgetValues.map(([key]) => key));
  if (query.isError) return <ErrorPanel error={operatorError(query.error)} onRetry={() => void query.refetch()} />;
  if (query.isPending) return <Skeleton />;
  return <dl>{budgetValues.map(([key, title]) => {
    const value = query.data.keys.find(row => row.key === key && row.sensitivity === "public")?.value;
    return <div key={key}><dt>{title}</dt><dd>{value === 0 ? "Без лимита" : typeof value === "number" ? value : "—"}</dd></div>;
  })}</dl>;
}

export function Quotas() {
  const { me } = useAuth();
  const { scope: { projectId, workspaceId } } = useScope();
  const scope = projectId ? `project:${projectId}` : workspaceId ? `workspace:${workspaceId}` : "instance";
  return <section>
    <h2>Квоты и лимиты</h2>
    <p>Квоты учётных записей провайдера проверяются на хосте командой <code>skm providers probe</code>.</p>
    {allowed(me, "config.read", projectId, workspaceId) && <>
      <h3>Лимиты выполнения · {escapeText(scope)}</h3>
      <ExecutionBudgets scope={scope} />
    </>}
  </section>;
}
