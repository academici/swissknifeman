import { useState } from "react";
import { useParams } from "react-router";
import { useExtensionAccess, useExtensionCommand, useResourceVersion } from "../../api/hooks/extensions";
import { operatorError } from "../../api/hooks/workspace";
import { CodeBlock } from "../../components/content/CodeBlock";
import { JsonView } from "../../components/data/JsonView";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Badge } from "../../components/primitives/Badge";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";

function Resource({ id, install, release }: { id: string; install: boolean; release: boolean }) {
  const query = useResourceVersion(id);
  const command = useExtensionCommand();
  const [action, setAction] = useState<"quarantine" | "release">();
  return <>
    {query.data && query.isStale && <Badge tone="warning">Данные устарели</Badge>}
    <QueryView query={query}>{resource => <>
      <h2>{escapeText(resource.kind + ":" + resource.key)} · {escapeText(resource.version)}</h2>
      <p>Версия пакета {escapeText(resource.pack_version_id)} · {escapeText(resource.digest)}</p>
      <h3>Происхождение</h3>
      {resource.manifest.provenance ? <JsonView value={resource.manifest.provenance} /> : <p>Сведения не указаны</p>}
      <h3>Манифест и совместимость</h3><JsonView value={resource.manifest} />
      <h3>Файлы</h3>
      <Table rows={resource.files} rowKey={f => f.path} empty="Нет файлов" columns={[
        { id: "path", header: "Имя", cell: f => escapeText(f.path) },
        { id: "size", header: "Байт", cell: f => f.size_bytes },
        { id: "digest", header: "Digest", cell: f => escapeText(f.digest) },
      ]} />
      {Object.entries(resource.bodies ?? {}).map(([path, body]) => <details key={path}>
        <summary>{escapeText(path)}</summary><CodeBlock text={body} />
      </details>)}
      {install && <>
        <Button disabled={command.status === "pending"} onClick={() => setAction("quarantine")}>Поместить в карантин</Button>
        {release && <Button disabled={command.status === "pending"} onClick={() => setAction("release")}>Снять карантин</Button>}
        {action && (action === "quarantine" || release) && <ConfirmDialog open requireReason title={action === "release" ? "Снять карантин" : "Поместить в карантин"}
          description={resource.key + " · " + resource.version} onClose={() => setAction(undefined)} onConfirm={reason => {
            command.submit({ action, reason, id: resource.resource_version_id });
            setAction(undefined);
          }} />}
      </>}
    </>}</QueryView>
    {install && command.error && <ErrorPanel error={operatorError(command.error)} onRetry={command.retry} />}
    {command.status === "success" && <p role="status">Состояние карантина обновлено</p>}
  </>;
}

export default function ResourcePage() {
  const { resourceVersionId } = useParams();
  const { read, install, release } = useExtensionAccess();
  return <section><h1>Ресурс расширения</h1>
    {read && resourceVersionId ? <Resource key={resourceVersionId} id={resourceVersionId} install={install} release={release} /> : <p role="alert">Нет доступа к ресурсу.</p>}
  </section>;
}
