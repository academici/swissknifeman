import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Health } from "../../api/generated/api";
import type { DoctorResult, ListDeadOutboxResult, MigrationStatusResult, RetryOutboxResult } from "../../api/generated/platform";
import { allowed, operatorError, segment, sendCommand, useCursor, withParams } from "../../api/hooks/workspace";
import { useIdempotentMutation } from "../../api/idempotency";
import { HttpTransport } from "../../api/transport";
import { useAuth } from "../../app/providers/AuthProvider";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Badge } from "../../components/primitives/Badge";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";

// Readiness is the one endpoint whose 503 JSON is a successful observation.
// Adapt only that wire response before HttpTransport's normal Problem handling.
const probes = new HttpTransport({
  getToken: () => null,
  fetch: async (path, init) => {
    const response = await fetch(path, { ...init, cache: "no-store" });
    if (path === "/health/ready" && response.status === 503 &&
        response.headers.get("content-type")?.split(";")[0] === "application/json") {
      const health = await response.clone().json().catch(() => null);
      if (health?.status === "not_ready") return Response.json(health, { headers: response.headers });
    }
    return response;
  },
});

function publicSummary(input: Health, live: boolean): Health {
  if (live && input.status === "live") return { status: "live" };
  const c = input.checks;
  if (live || !["ready", "not_ready"].includes(input.status) || !c ||
    !["ok", "fail"].includes(c.database) || !["ok", "fail"].includes(c.background) ||
    !["ok", "not_migrated", "too_new", "invalid"].includes(c.schema)) throw new Error("Некорректный ответ проверки");
  return { status: input.status, checks: { database: c.database, schema: c.schema, background: c.background } };
}

function Probe({ live }: { live: boolean }) {
  const path = live ? "/health/live" : "/health/ready";
  const query = useQuery({
    queryKey: ["health", path], refetchInterval: 15_000, retry: false,
    queryFn: async ({ signal }) => publicSummary((await probes.request<Health>("GET", path, { signal })).data, live),
  });
  return <section><h2>{live ? "Доступность" : "Готовность"}</h2>
    <QueryView query={{ data: query.data, error: operatorError(query.error) }}>{health => <>
      <Badge tone={health.status === "not_ready" ? "warning" : "success"}>{escapeText(health.status)}</Badge>
      {health.checks && <dl className="data-list">{Object.entries(health.checks).map(([key, value]) =>
        <div key={key}><dt>{escapeText(key)}</dt><dd>{escapeText(value)}</dd></div>)}</dl>}
    </>}</QueryView>
  </section>;
}

function useHealthRead<T>(path: string, group = path) {
  const { transport } = useAuth();
  const query = useQuery({
    queryKey: ["health", group, path], refetchInterval: 15_000, retry: false,
    queryFn: async ({ signal }) => (await transport.request<T>("GET", path, { signal })).data,
  });
  return { data: query.data, error: operatorError(query.error) };
}

function Checks({ path }: { path: string }) {
  const query = useHealthRead<DoctorResult>(path);
  return <QueryView query={query}>{view => <Table rows={view.checks} rowKey={r => r.id} empty="Нет проверок" columns={[
    { id: "id", header: "Проверка", cell: r => escapeText(r.id) },
    { id: "status", header: "Статус", cell: r => escapeText(r.status) },
    { id: "message", header: "Результат", cell: r => escapeText(r.message) },
    { id: "hint", header: "Подсказка", cell: r => r.hint && escapeText(r.hint) },
  ]} />}</QueryView>;
}

function Diagnostics() {
  const [only, setOnly] = useState("");
  return <section><h2>Подробное состояние</h2><Checks path="/health/details" />
    <h2>Doctor</h2>
    <form onSubmit={e => {
      e.preventDefault();
      setOnly(String(new FormData(e.currentTarget).get("only")).split(/[,\s]+/u).filter(Boolean).join(","));
    }}>
      <label>Коды проверок через запятую<input name="only" /></label>
      <Button type="submit">Применить фильтр</Button>
    </form>
    <Checks path={withParams("/api/v1/doctor", { only })} />
  </section>;
}

function Migrations() {
  const query = useHealthRead<MigrationStatusResult>("/api/v1/admin/migrations");
  return <section><h2>Миграции</h2><QueryView query={query}>{view => <>
    <p>{escapeText(view.state)} · Версия БД {view.db_version} · Версия приложения {view.known_version}</p>
    <Table rows={view.migrations} rowKey={r => r.version} empty="Нет миграций" columns={[
      { id: "version", header: "Версия", cell: r => r.version },
      { id: "name", header: "Название", cell: r => escapeText(r.name) },
      { id: "state", header: "Состояние", cell: r => escapeText(r.state) },
    ]} />
  </>}</QueryView></section>;
}

function Outbox() {
  const { transport } = useAuth();
  const client = useQueryClient();
  const cursor = useCursor("/api/v1/admin/outbox/dead");
  const query = useHealthRead<ListDeadOutboxResult>(cursor.path, "outbox");
  const retry = useIdempotentMutation(async (id: string, key) => {
    const result = await sendCommand<RetryOutboxResult>(transport, { path: `/admin/outbox/${segment(id)}/retry` }, key);
    await client.invalidateQueries({ queryKey: ["health", "outbox"] });
    return result.data;
  });
  return <section><h2>Недоставленные события</h2>
    <QueryView query={query}>{view => <>
      <Table rows={view.items} rowKey={r => r.outbox_id} empty="Нет недоставленных событий" columns={[
        { id: "event", header: "Событие", cell: r => escapeText(r.event_id) },
        { id: "destination", header: "Назначение", cell: r => escapeText(r.destination) },
        { id: "attempts", header: "Попытки", cell: r => r.attempts },
        { id: "retry", header: "Действие", cell: r => <Button disabled={retry.status === "pending"} onClick={() => retry.submit(r.outbox_id)}>Повторить доставку</Button> },
      ]} /><Pagination {...cursor} next={view.next} />
    </>}</QueryView>
    {retry.error && <ErrorPanel error={operatorError(retry.error)} onRetry={retry.retry} />}
    {retry.data && <p role="status">Возвращено в очередь · {retry.data.requeued}</p>}
  </section>;
}

export default function HealthPage() {
  const { me } = useAuth();
  return <section><h1>Состояние системы</h1>
    <Probe live /><Probe live={false} />
    {allowed(me, "config.read") && <Diagnostics />}
    {/* The degraded route has a bearer token and the server checks admin.storage. */}
    {(!me || allowed(me, "admin.storage")) && <Migrations />}
    {allowed(me, "admin.events") && <Outbox />}
  </section>;
}
