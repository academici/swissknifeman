import { useState } from "react";
import { useParams } from "react-router";
import { useExtensionAccess, useExtensionCommand, usePack } from "../../api/hooks/extensions";
import { operatorError } from "../../api/hooks/workspace";
import { JsonView } from "../../components/data/JsonView";
import { Table } from "../../components/data/Table";
import { RelativeTime } from "../../components/data/RelativeTime";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Badge } from "../../components/primitives/Badge";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";
import type { PackViewVersionsItem } from "../../api/generated/extensions";

function Pack({ id, install }: { id: string; install: boolean }) {
  const query = usePack(id);
  const command = useExtensionCommand();
  const [remove, setRemove] = useState<PackViewVersionsItem>();
  return <>
    {query.data && query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={query}>{pack => <>
      <h2>{escapeText(pack.title)}</h2>
      <p>{escapeText(pack.slug)} · {escapeText(pack.trust)} · Приоритет {pack.priority}</p>
      <Table rows={pack.versions} rowKey={v => v.version_id} empty="Нет версий" columns={[
        { id: "version", header: "Версия", cell: v => escapeText(v.version) },
        { id: "state", header: "Состояние", cell: v => escapeText(v.state) },
        { id: "at", header: "Установлена", cell: v => <RelativeTime value={v.installed_at} /> },
        ...(install ? [{ id: "remove", header: "Действия", cell: (v: PackViewVersionsItem) => v.state === "active" &&
          <Button disabled={command.status === "pending"} onClick={() => setRemove(v)}>Удалить версию {escapeText(v.version)}</Button> }] : []),
      ]} />
      <h3>Ресурсы по типам</h3><JsonView value={pack.resources_by_kind} />
      <h3>Манифест и переопределения</h3><JsonView value={pack.manifest} />
    </>}</QueryView>
    {install && remove && <ConfirmDialog open destructive title={`Удалить версию ${remove.version}?`} onClose={() => setRemove(undefined)}
      onConfirm={() => { command.submit({ action: "delete", id: remove.version_id }); setRemove(undefined); }} />}
    {install && command.error && <ErrorPanel error={operatorError(command.error)} onRetry={command.retry} />}
  </>;
}

export default function PackPage() {
  const { packId } = useParams();
  const { read, install } = useExtensionAccess();
  return <section><h1>Пакет расширений</h1>
    {read && packId ? <Pack key={packId} id={packId} install={install} /> : <p role="alert">Нет доступа к пакету.</p>}
  </section>;
}
