import { useState } from "react";
import { Navigate, useParams } from "react-router";
import { FileOriginValues } from "../../api/generated/artifacts";
import { useFiles } from "../../api/hooks/artifacts";
import { allowed, segment, useProject, withParams } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { SafeLink } from "../../components/content/SafeLink";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";
import UploadDialog from "./UploadDialog";

export function WorkspaceFiles({ workspaceId, projectId, active }: { workspaceId: string; projectId: string | null; active: boolean }) {
  const { me } = useAuth();
  const [state, setState] = useState("active");
  const [origin, setOrigin] = useState("");
  const canUpload = active && allowed(me, "file.write", workspaceId) && allowed(me, "file.write", projectId, workspaceId);
  const { query, cursor } = useFiles(workspaceId, projectId, state, origin);
  return <section>
    {canUpload && <UploadDialog key={projectId ?? workspaceId} workspaceId={workspaceId} projectId={projectId} />}
    <label>Состояние файла<select value={state} onChange={e => setState(e.target.value)}>
      <option value="">Все</option><option>active</option><option>trashed</option>
    </select></label>
    <label>Источник<select value={origin} onChange={e => setOrigin(e.target.value)}>
      <option value="">Все</option>{FileOriginValues.map(value => <option key={value}>{value}</option>)}
    </select></label>
    <QueryView query={query}>{page => <>
      <Table rows={page.items} rowKey={row => row.file_id} empty="Нет файлов" columns={[
        { id: "title", header: "Название", cell: row => <SafeLink href={withParams("/files/" + segment(row.file_id), { workspace_id: row.workspace_id, project_id: row.project_id })}>{row.title}</SafeLink> },
        { id: "classification", header: "Классификация", cell: row => escapeText(row.classification) },
        { id: "origin", header: "Источник", cell: row => escapeText(row.origin) },
        { id: "state", header: "Состояние", cell: row => escapeText(row.state) },
      ]} />
      <Pagination next={page.next} {...cursor} />
    </>}</QueryView>
  </section>;
}

export default function FilesPage() {
  const { projectId = "" } = useParams();
  const { scope } = useScope();
  const project = useProject(projectId);
  return <section><h1>Файлы</h1><QueryView query={project}>{data =>
    scope.workspaceId && data.workspace_id !== scope.workspaceId
      ? <Navigate replace to={`/p/${segment(projectId)}/files?workspace_id=${segment(data.workspace_id)}`} />
      : <WorkspaceFiles key={data.project_id} active={data.state === "active"} workspaceId={data.workspace_id} projectId={data.project_id} />}</QueryView></section>;
}
