import { version as packageVersion } from "../../../package.json";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { HostArchValues, HostOsValues, type HostArch, type HostOs, type SetWorkerState, type WorkerView } from "../../api/generated/workspace";
import type { Uuid } from "../../api/generated/kernel";
import { allowed, operatorError, registerWorker, useHost, useHosts, useWorkers, useWorkerState } from "../../api/hooks/workspace";
import { keys } from "../../api/keys";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { useStream } from "../../app/providers/StreamProvider";
import { JsonView } from "../../components/data/JsonView";
import { Pagination } from "../../components/data/Pagination";
import { RelativeTime } from "../../components/data/RelativeTime";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Badge } from "../../components/primitives/Badge";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { Dialog } from "../../components/primitives/Dialog";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";

function Registration({ workspaceId }: { workspaceId: string }) {
  const { transport } = useAuth();
  const client = useQueryClient();
  const [pending, setPending] = useState(false);
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<unknown>();
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending || secret) return;
    const form = e.currentTarget;
    const fields = new FormData(form);
    const field = (name: string) => String(fields.get(name)).trim();
    const list = (name: string) => field(name).split(/[,\s]+/u).filter(Boolean);
    setError(null);
    setPending(true);
    try {
      const token = await registerWorker(transport, workspaceId, {
        host_id: field("host") as Uuid, display_name: field("name"), capabilities: {
          runtimes: list("runtimes"), isolation_profiles: list("profiles"), labels: list("labels"),
          max_concurrency: Number(field("concurrency")), skm_version: field("version"),
          platform: { os: field("os") as HostOs, arch: field("arch") as HostArch },
        },
      });
      form.reset();
      setSecret(token);
      void client.invalidateQueries({ queryKey: keys.workspace(workspaceId) });
    } catch (failure) {
      setError(operatorError(failure));
    } finally {
      setPending(false);
    }
  }
  return <section>
    <h2>Регистрация воркера</h2>
    <form onSubmit={submit}>
      <label>Имя воркера<input name="name" required /></label>
      <label>ID хоста<input name="host" required /></label>
      <label>ОС<select name="os">{HostOsValues.map(os => <option key={os}>{os}</option>)}</select></label>
      <label>Архитектура<select name="arch">{HostArchValues.map(arch => <option key={arch}>{arch}</option>)}</select></label>
      <label>Версия SKM<input name="version" required placeholder={packageVersion} /></label>
      <label>Среды выполнения через запятую<input name="runtimes" /></label>
      <label>Профили изоляции через запятую<input name="profiles" required placeholder="worktree" /></label>
      <label>Метки через запятую<input name="labels" /></label>
      <label>Параллельные задания<input name="concurrency" type="number" defaultValue={1} min={1} max={64} required /></label>
      <Button type="submit" disabled={pending || Boolean(secret)}>Зарегистрировать воркера</Button>
    </form>
    {error != null && <ErrorPanel error={error} />}
    {secret && <Dialog open title="Одноразовый токен воркера" onClose={() => setSecret("")}>
      <p>Сохраните токен до закрытия окна.</p><code>{escapeText(secret)}</code>
    </Dialog>}
  </section>;
}

const targetStates = ["online", "draining", "retired"] as const;

function Workers({ workspaceId, manage }: { workspaceId: string; manage: boolean }) {
  const { query, cursor } = useWorkers(workspaceId);
  const { stale } = useStream();
  const command = useWorkerState();
  const [target, setTarget] = useState<{ worker: WorkerView; state: SetWorkerState["state"] }>();
  return <>
    {stale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={query}>{page => <>
      <Table rows={page.items} rowKey={row => row.worker_id} empty="Нет воркеров" columns={[
        { id: "name", header: "Воркер", cell: w => escapeText(w.display_name) },
        { id: "host", header: "Хост", cell: w => escapeText(w.host_id) },
        { id: "state", header: "Состояние", cell: w => <Badge>{escapeText(w.state)}{(w.state === "retired" || w.state === "offline") && " · неактивен"}</Badge> },
        { id: "heartbeat", header: "Последний heartbeat", cell: w => w.last_heartbeat_at ? <RelativeTime value={w.last_heartbeat_at} /> : "Не получен" },
        { id: "capabilities", header: "Возможности и изоляция", cell: w => <JsonView value={w.capabilities} /> },
        ...(manage ? [{ id: "actions", header: "Изменить состояние", cell: (w: WorkerView) => w.state !== "retired" &&
          targetStates.filter(s => s !== w.state).map(state => <Button key={state} disabled={command.status === "pending"}
            onClick={() => setTarget({ worker: w, state })}>{state}</Button>) }] : []),
      ]} /><Pagination {...cursor} next={page.next} />
    </>}</QueryView>
    {manage && target && <ConfirmDialog open destructive={target.state === "retired"} title={`${target.worker.display_name} → ${target.state}`}
      description={target.state === "retired" ? "Токены воркера будут отозваны." : "Изменить состояние воркера?"}
      onClose={() => setTarget(undefined)} onConfirm={() => {
        command.submit(target);
        setTarget(undefined);
      }} />}
    {command.error && <ErrorPanel error={operatorError(command.error)} />}
  </>;
}

function HostDetail({ id }: { id: string }) {
  const query = useHost(id);
  return <>
    {query.data && query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={query}>{host => <>
      <h3>{escapeText(host.name)}</h3><p>{escapeText(host.host_id)} · {escapeText(host.platform.os)} / {escapeText(host.platform.arch)}</p>
      <p>Зарегистрирован <RelativeTime value={host.registered_at} /></p>
      {host.last_seen_at && <p>Последняя связь <RelativeTime value={host.last_seen_at} /></p>}
    </>}</QueryView>
  </>;
}

function Hosts({ workspaceId }: { workspaceId: string | null }) {
  const { query, cursor } = useHosts(workspaceId);
  const [id, setId] = useState("");
  return <section>
    <h2>Хосты</h2>
    {query.data && query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={query}>{page => <>
      <Table rows={page.items} rowKey={h => h.host_id} empty="Нет хостов" columns={[
        { id: "name", header: "Имя", cell: h => <Button onClick={() => setId(h.host_id)}>{escapeText(h.name)}</Button> },
        { id: "id", header: "ID", cell: h => escapeText(h.host_id) },
        { id: "state", header: "Состояние", cell: h => escapeText(h.state) },
      ]} /><Pagination {...cursor} next={page.next} />
    </>}</QueryView>
    {id && <HostDetail id={id} />}
  </section>;
}

export default function WorkersPage() {
  const { me } = useAuth();
  const { scope: { workspaceId } } = useScope();
  const read = me?.modules.workspace !== false && allowed(me, "workspace.read", workspaceId);
  const manage = me?.modules.workspace !== false && allowed(me, "worker.register", workspaceId);
  return <section><h1>Воркеры</h1>
    {!workspaceId && <p>Выберите рабочее пространство для просмотра воркеров.</p>}
    {workspaceId && read && <Workers key={`workers-${workspaceId}`} workspaceId={workspaceId} manage={manage} />}
    {!read && <p role="alert">Нет доступа к списку воркеров и хостов.</p>}
    {read && <Hosts key={`hosts-${workspaceId}`} workspaceId={workspaceId} />}
    {manage && workspaceId && <Registration key={`register-${workspaceId}`} workspaceId={workspaceId} />}
  </section>;
}
