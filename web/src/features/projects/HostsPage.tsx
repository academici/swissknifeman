import { useState } from "react";
import { HostArchValues, HostOsValues, type HostView } from "../../api/generated/workspace";
import { allowed, useCommand, usePage, withParams } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { CopyId } from "../../components/data/CopyId";
import { Badge } from "../../components/primitives/Badge";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";

export default function HostsPage({ workspaceId }: { workspaceId: string }) {
  const { me } = useAuth();
  const [name, setName] = useState("");
  const [state, setState] = useState("");
  const { query, cursor } = usePage<HostView>(withParams("/hosts", { workspace_id: workspaceId, name, state }), undefined, true);
  const command = useCommand(workspaceId);
  return <section>
    <h2>Хосты</h2>
    {query.data && query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <label>Поиск по имени<input value={name} onChange={e => setName(e.target.value)} /></label>
    <label>Состояние хоста<select value={state} onChange={e => setState(e.target.value)}>
      <option value="">Все</option><option>active</option><option>retired</option>
    </select></label>
    <QueryView query={query}>{page => <>
      <Table rows={page.items} rowKey={h => h.host_id} empty="Нет хостов" columns={[
        { id: "name", header: "Имя", cell: h => escapeText(h.name) },
        { id: "id", header: "ID", cell: h => <CopyId id={h.host_id} /> },
        { id: "platform", header: "Платформа", cell: h => escapeText(`${h.platform.os} / ${h.platform.arch}`) },
        { id: "state", header: "Состояние", cell: h => <StatusBadge status={h.state} /> },
      ]} /><Pagination {...cursor} next={page.next} />
    </>}</QueryView>
    {allowed(me, "host.manage") && <form onSubmit={e => {
      e.preventDefault();
      const fields = new FormData(e.currentTarget);
      command.mutate({ path: "/hosts", body: { name: fields.get("name"), platform: { os: fields.get("os"), arch: fields.get("arch") } } });
    }}>
      <label>Имя хоста<input name="name" required /></label>
      <label>ОС<select name="os">{HostOsValues.map(os => <option key={os}>{os}</option>)}</select></label>
      <label>Архитектура<select name="arch">{HostArchValues.map(arch => <option key={arch}>{arch}</option>)}</select></label>
      <Button type="submit" disabled={command.isPending}>Зарегистрировать хост</Button>
    </form>}
    {command.error && <ErrorPanel error={command.error} />}
  </section>;
}
