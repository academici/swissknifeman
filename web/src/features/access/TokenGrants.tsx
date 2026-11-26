import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ScopeGrantSpec, WhoAmIView } from "../../api/generated/access";
import type { ProjectSummaryView, WorkspaceSummaryView } from "../../api/generated/workspace";
import { operatorError, segment, usePage } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { Pagination } from "../../components/data/Pagination";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";

export type ProjectGrant = {
  project: ProjectSummaryView;
  workspaceId: WorkspaceSummaryView["workspace_id"];
  permissions: ScopeGrantSpec["permissions"];
};
const ownerPermissions = new Set(["principal.manage", "membership.manage", "token.any", "config.lock"]);

function Permissions({ grant, update, remove }: {
  grant: ProjectGrant;
  update(permissions: ProjectGrant["permissions"]): void;
  remove(): void;
}) {
  const { transport } = useAuth();
  const { project, permissions } = grant;
  const query = useQuery({
    queryKey: ["access", "me", project.project_id],
    queryFn: async ({ signal }) => (await transport.request<WhoAmIView>(
      "GET", `/api/v1/me?scope_id=${segment(project.project_id)}`, { signal },
    )).data,
  });
  const owner = query.data?.memberships.some(m => m.scope_kind === "instance" && m.role === "owner");
  const choices = query.data?.effective_permissions.filter(p =>
    !p.startsWith("system.") && (owner || !ownerPermissions.has(p))) ?? [];
  return <fieldset>
    <legend>{escapeText(project.title)} · {escapeText(project.project_id)}</legend>
    {query.isPending && <p role="status">Загрузка разрешений…</p>}
    {query.isError && <ErrorPanel error={operatorError(query.error)} onRetry={() => void query.refetch()} />}
    {query.isSuccess && choices.length === 0 && <p>Нет доступных разрешений.</p>}
    {choices.map(permission => <label key={permission}>
      <input type="checkbox" checked={permissions.includes(permission)} onChange={event =>
        update(event.currentTarget.checked ? [...permissions, permission] : permissions.filter(p => p !== permission))
      } /> {escapeText(permission)}
    </label>)}
    <Button onClick={remove}>Убрать проект</Button>
  </fieldset>;
}

export function TokenGrants({ workspace, onWorkspace, grants, onGrants }: {
  workspace: WorkspaceSummaryView | undefined;
  onWorkspace(workspace: WorkspaceSummaryView | undefined): void;
  grants: readonly ProjectGrant[];
  onGrants(grants: readonly ProjectGrant[]): void;
}) {
  const { query, cursor } = usePage<WorkspaceSummaryView>("/workspaces?state=active", ["access", "token-workspaces"], true);
  const workspaces = query.data?.items ?? [];
  return <>
    <label>Рабочее пространство
      <select value={workspace?.workspace_id ?? ""} onChange={event =>
        onWorkspace(workspaces.find(w => w.workspace_id === event.currentTarget.value))
      }>
        <option value="">Выберите пространство</option>
        {workspace && !workspaces.some(w => w.workspace_id === workspace.workspace_id) &&
          <option value={workspace.workspace_id}>{escapeText(workspace.title)}</option>}
        {workspaces.map(w => <option key={w.workspace_id} value={w.workspace_id}>{escapeText(w.title)}</option>)}
      </select>
    </label>
    {query.isPending && <p role="status">Загрузка пространств…</p>}
    {query.isError && <ErrorPanel error={operatorError(query.error)} onRetry={() => void query.refetch()} />}
    {query.data && <Pagination {...cursor} next={query.data.next} />}
    {workspace && <ProjectPicker key={workspace.workspace_id} workspace={workspace} grants={grants}
      add={project => onGrants([...grants, { project, workspaceId: workspace.workspace_id, permissions: [] }])} />}
    {grants.map(grant => {
      const id = grant.project.project_id;
      return <Permissions key={id} grant={grant}
        update={permissions => onGrants(grants.map(g => g === grant ? { ...g, permissions } : g))}
        remove={() => onGrants(grants.filter(g => g !== grant))} />;
    })}
  </>;
}

function ProjectPicker({ workspace, grants, add }: {
  workspace: WorkspaceSummaryView;
  grants: readonly ProjectGrant[];
  add(project: ProjectSummaryView): void;
}) {
  const [projectId, setProjectId] = useState("");
  const path = `/workspaces/${segment(workspace.workspace_id)}/projects?state=active`;
  const { query, cursor } = usePage<ProjectSummaryView>(path, ["access", "token-projects", workspace.workspace_id], true);
  const projects = (query.data?.items ?? []).filter(p => !grants.some(g => g.project.project_id === p.project_id));
  const selected = projects.find(p => p.project_id === projectId);
  return <>
    <label>Проект токена
      <select value={selected?.project_id ?? ""} onChange={event => setProjectId(event.currentTarget.value)}>
        <option value="">Выберите проект</option>
        {projects.map(p => <option key={p.project_id} value={p.project_id}>{escapeText(p.title)}</option>)}
      </select>
    </label>
    <Button disabled={!selected || grants.length >= 100} onClick={() => {
      if (selected) { add(selected); setProjectId(""); }
    }}>Добавить проект</Button>
    {query.isPending && <p role="status">Загрузка проектов…</p>}
    {query.isError && <ErrorPanel error={operatorError(query.error)} onRetry={() => void query.refetch()} />}
    {query.data && <Pagination {...cursor} next={query.data.next} />}
  </>;
}
