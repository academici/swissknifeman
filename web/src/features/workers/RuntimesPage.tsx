import { useState } from "react";
import { ApiError } from "../../api/errors";
import { RoleIdValues, type RoleId } from "../../api/generated/runtimes";
import { useCapabilities, useModels, useRouting, useRuntimes } from "../../api/hooks/runtimes";
import { allowed, operatorError } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { HostPicker } from "../../components/data/HostPicker";
import { JsonView } from "../../components/data/JsonView";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Badge } from "../../components/primitives/Badge";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";
import { HostRoutingSettings, Quotas } from "./RuntimeSettings";

function field(value: unknown): string {
  return typeof value === "string" ? escapeText(value) : "—";
}

function Capabilities({ id, version }: { id: string; version: string | null }) {
  const query = useCapabilities(id, version);
  return <section><h3>Возможности · {escapeText(id)} {version && escapeText(version)}</h3>
    {query.data && query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={query}>{view => <Table rows={view.records} rowKey={r => r.capability} empty="Нет сведений о возможностях" columns={[
      { id: "name", header: "Возможность", cell: r => escapeText(r.capability) },
      { id: "status", header: "Поддержка", cell: r => <Badge tone={r.status === "native" || r.status === "adapted" ? "success" : "neutral"}>{escapeText(r.status)}</Badge> },
      { id: "source", header: "Основание", cell: r => escapeText(r.source + " · " + r.evidence) },
      { id: "limits", header: "Ограничения", cell: r => escapeText(r.limitations) },
    ]} />}</QueryView>
  </section>;
}

function ModelGuideline({ runtime, model }: { runtime: string; model: string }) {
  const query = useModels(runtime, model);
  const guideline = query.data?.models.find(row => row.id === model)?.guideline;
  return <section>
    <h3>Рекомендации для модели {escapeText(model)}</h3>
    {query.isPending ? <Skeleton /> : query.error instanceof ApiError && query.error.status === 404
      ? <p>Для модели нет рекомендаций.</p>
      : query.isError ? <ErrorPanel error={operatorError(query.error)} onRetry={() => void query.refetch()} />
        : guideline ? <JsonView value={guideline} /> : <p>Для модели нет рекомендаций.</p>}
  </section>;
}

function Catalog({ host }: { host: string }) {
  const query = useRuntimes(host);
  const [selected, setSelected] = useState<{ id: string; version: string | null }>();
  const [guideline, setGuideline] = useState<{ runtime: string; model: string }>();
  const [sync, setSync] = useState<"idle" | "pending" | "complete" | "failed">("idle");
  const models = useModels(selected?.id ?? "");
  function select(id: string, version: string | null) {
    setSelected({ id, version });
    setGuideline(undefined);
  }
  async function syncCatalog() {
    setSync("pending");
    const result = await models.refetch({ cancelRefetch: false });
    setSync(result.isSuccess ? "complete" : "failed");
  }
  return <>
    {query.data && query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={query}>{view => <Table rows={view.items} rowKey={r => r.runtime_id} empty="Нет сред выполнения" columns={[
      { id: "name", header: "Среда", cell: r => <Button onClick={() => select(r.runtime_id, null)}>{escapeText(r.runtime_id)}</Button> },
      { id: "adapter", header: "Адаптер", cell: r => escapeText(r.adapter_version) },
      { id: "allowed", header: "Допуск", cell: r => r.allowed_in_scope ? "Разрешена" : "Запрещена" },
      { id: "hosts", header: "Установки и авторизация", cell: r => r.installations.length === 0 ? "Установка не обнаружена" :
        <ul>{r.installations.map(i => <li key={i.host_id}><Button onClick={() => select(r.runtime_id, i.version)}>
          {escapeText(i.host_id)} · {escapeText(i.version ?? "Версия неизвестна")}
        </Button> · {escapeText(i.auth_state)}</li>)}</ul> },
    ]} />}</QueryView>
    {selected && <Capabilities id={selected.id} version={selected.version} />}
    <h2>Модели{selected && " · " + escapeText(selected.id)}</h2>
    {selected && <Button onClick={() => { setSelected(undefined); setGuideline(undefined); }}>Все модели</Button>}
    <Button onClick={() => void syncCatalog()} disabled={sync === "pending"}>Синхронизировать каталог</Button>
    <p>Загружает опубликованный каталог SKM. Подготовка обновления из внешних источников выполняется командой <code>skm runtime sync</code>.</p>
    {sync !== "idle" && <p role="status">{sync === "pending" ? "Загрузка каталога…" :
      sync === "complete" ? "Опубликованный каталог загружен." : "Не удалось загрузить каталог."}</p>}
    {models.data && models.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={models}>{view => <>
      <p>Версия каталога {escapeText(view.catalog_version)} {view.stale && <Badge tone="warning">Каталог устарел</Badge>}</p>
      <Table rows={view.models} rowKey={model => String(model.runtime_id) + "/" + String(model.id)} empty="Нет моделей" columns={[
        { id: "model", header: "Модель", cell: m => field(m.display_name ?? m.id) },
        { id: "runtime", header: "Среда", cell: m => field(m.runtime_id) },
        { id: "status", header: "Статус", cell: m => field(m.status) },
        { id: "details", header: "Параметры", cell: m => <JsonView value={m} /> },
        { id: "guideline", header: "Рекомендации", cell: m => {
          const { runtime_id, id } = m;
          return typeof runtime_id === "string" && typeof id === "string" &&
            <Button onClick={() => setGuideline({ runtime: runtime_id, model: id })}>Рекомендации · {escapeText(id)}</Button>;
        } },
      ]} />
    </>}</QueryView>
    {guideline && <ModelGuideline runtime={guideline.runtime} model={guideline.model} />}
  </>;
}

function Routing({ role, host }: { role: RoleId; host: string }) {
  const query = useRouting(role, host);
  return <>
    {query.data && query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={query}>{view => <>
      {view.error && <p role="alert">Выбор среды недоступен · {escapeText(view.error.code)}</p>}
      {view.decision && <p>Выбрана среда {field(view.decision.runtime_id)} · Модель {field(view.decision.model)}</p>}
      <h3>Условия допуска</h3><JsonView value={view.admission} />
      <Table rows={view.rejected} rowKey={r => JSON.stringify(r)} empty="Нет отклонённых кандидатов" columns={[
        { id: "runtime", header: "Среда", cell: r => field(r.runtime_id) },
        { id: "model", header: "Модель", cell: r => field(r.model) },
        { id: "reason", header: "Основание", cell: r => <JsonView value={r} /> },
      ]} />
      <h3>Параметры маршрутизации</h3><JsonView value={{ decision: view.decision, config: view.config }} />
    </>}</QueryView>
  </>;
}

function Runtimes() {
  const [host, setHost] = useState("");
  const [role, setRole] = useState<RoleId>("executor");
  const [explain, setExplain] = useState(false);
  return <>
    <h2>Хосты</h2>
    <HostPicker value={host} onChange={setHost} empty="Все хосты" />
    <Catalog key={host} host={host} />
    <Quotas />
    <h2>Маршрутизация</h2>
    {host ? <HostRoutingSettings host={host} /> : <p>Выберите хост для просмотра подстановок маршрутов.</p>}
    <label>Роль<select value={role} onChange={e => setRole(e.target.value as RoleId)}>
      {RoleIdValues.map(r => <option key={r}>{r}</option>)}
    </select></label>
    <Button onClick={() => setExplain(true)}>Объяснить выбор</Button>
    {explain && <Routing role={role} host={host} />}
  </>;
}

export default function RuntimesPage() {
  const { me } = useAuth();
  return <section><h1>Среды выполнения</h1>
    {me?.modules.runtimes !== false && allowed(me, "runtime.read") ? <Runtimes /> : <p role="alert">Нет доступа к средам выполнения.</p>}
  </section>;
}
