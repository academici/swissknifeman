import { lazy, Suspense, useState } from "react";
import { Navigate, useParams } from "react-router";
import type { GetHookPolicy, ProjectionSummaryView } from "../../api/generated/integrations";
import type { ProjectView, WorkspaceView } from "../../api/generated/workspace";
import { useIntegrations } from "../../api/hooks/integrations";
import { allowed, segment, useCommand, useProject, useRead } from "../../api/hooks/workspace";
import { keys } from "../../api/keys";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { SafeLink } from "../../components/content/SafeLink";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { Tabs } from "../../components/primitives/Tabs";
import { escapeText } from "../../lib/safeText";
import { WorkspaceFiles } from "../files/FilesPage";
import { ArchiveAction } from "../workspaces/WorkspacePage";
import { QueryView } from "../workspaces/WorkspacesPage";
import { MembersPanel } from "../access/MembersPanel";
import ProjectReposTab from "./ProjectReposTab";

const Plans = lazy(() => import("../plans/PlansPage"));
const Runs = lazy(() => import("../runs/RunsPage"));
const Autopilot = lazy(() => import("../autopilot/AutopilotTab"));

function Integrations({ project }: { project: ProjectView }) {
  const { me } = useAuth();
  const { workspace_id: ws, project_id: id } = project;
  const [target, setTarget] = useState<GetHookPolicy["target"]>("codex");
  const [selected, setSelected] = useState<ProjectionSummaryView | null>(null);
  const data = useIntegrations(ws, id, target, selected);
  const command = useCommand(ws);
  const base = `/workspaces/${segment(ws)}`;
  return <>
    <h2>Проекции</h2>
    <QueryView query={data.projections}>{page => <>
      <Table rows={page.items} rowKey={row => row.projection_id} empty="Нет проекций" columns={[
        { id: "target", header: "Цель", cell: row => escapeText(row.target) },
        { id: "state", header: "Состояние", cell: row => escapeText(row.state) },
        { id: "desired", header: "Конфигурация", cell: row => <Button onClick={() => setSelected(row)}>Показать конфигурацию</Button> },
      ]} /><Pagination next={page.next_cursor} {...data.projectionsPage} />
    </>}</QueryView>
    {selected && <QueryView query={data.desired}>{view => <JsonView value={view} />}</QueryView>}
    <h2>Политика хуков</h2>
    <label>Цель<select value={target} onChange={e => setTarget(e.target.value as GetHookPolicy["target"])}>
      {["antigravity", "claude_code", "codex", "cursor", "grok"].map(t => <option key={t}>{t}</option>)}</select></label>
    <QueryView query={data.policy}>{view => <JsonView value={view} />}</QueryView>
    <h2>Подписки</h2>
    <QueryView query={data.subscriptions}>{page => <Table rows={page.items} rowKey={row => row.id} empty="Нет подписок" columns={[
      { id: "id", header: "Подписка", cell: row => escapeText(row.id) },
      { id: "target", header: "Цель", cell: row => escapeText(row.target_summary) },
      { id: "test", header: "Проверка", cell: row => row.execution_location === "control_plane" && allowed(me, "hook.manage", id, ws) &&
        <Button disabled={command.isPending} onClick={() => command.mutate({ path: base + "/hook-subscriptions/" + segment(row.id) + "/test", body: { project_id: id } })}>Тест подписки</Button> },
    ]} />}</QueryView>
    <h2>Доставки пространства</h2>
    <QueryView query={data.deliveries}>{page => <>
      <Table rows={page.items} rowKey={row => row.delivery_id} empty="Нет доставок" columns={[
        { id: "subscription", header: "Подписка", cell: row => escapeText(row.subscription_id) },
        { id: "state", header: "Состояние", cell: row => escapeText(row.state) },
        { id: "retry", header: "Действия", cell: row => row.state === "dead" && allowed(me, "hook.manage", ws) &&
          <Button disabled={command.isPending} onClick={() => command.mutate({ path: base + "/hook-deliveries/retry", body: { delivery_ids: [row.delivery_id] } })}>Повторить доставку</Button> },
      ]} /><Pagination next={page.next_cursor} {...data.deliveryPage} />
    </>}</QueryView>
    {command.error && <ErrorPanel error={command.error} />}
  </>;
}

function ProjectDetail({ project }: { project: ProjectView }) {
  const { me } = useAuth();
  const [active, setActive] = useState("Overview");
  const { project_id: id, workspace_id: ws } = project;
  const workspace = useRead<WorkspaceView>(keys.workspace(ws), "/workspaces/" + segment(ws));
  const tabs = [
    { id: "Overview", content: <><dl><KeyValue label="Описание" value={project.description} /><KeyValue label="Состояние" value={project.state} /></dl>
      {workspace.data && <SafeLink href={`/w/${segment(workspace.data.slug)}?workspace_id=${segment(ws)}`}>{workspace.data.title}</SafeLink>}</> },
    { id: "Plans", content: <Plans /> },
    { id: "Runs", content: <Runs /> },
    { id: "Autopilot", content: <Autopilot /> },
    { id: "Repositories", content: <ProjectReposTab project={project} /> },
    { id: "Files", content: <WorkspaceFiles active={project.state === "active"} workspaceId={ws} projectId={id} /> },
    { id: "Integrations", content: <Integrations project={project} /> },
    { id: "Members", content: active === "Members" ? <MembersPanel scopeId={id} ancestors={[id, ws]} /> : null },
    { id: "Settings", content: <><SafeLink href={`/settings?scope=project:${segment(id)}&workspace_id=${segment(ws)}&project_id=${segment(id)}`}>Настройки проекта</SafeLink>
      {project.state === "active" && allowed(me, "project.manage", id, ws) &&
        <ArchiveAction path={`/projects/${segment(id)}/archive`} workspaceId={ws} version={project.row_version} />}</> },
  ];
  return <><h2>{escapeText(project.title)}</h2><Tabs label="Проект" active={active} onSelect={setActive} tabs={tabs.map(tab => ({ ...tab, label: tab.id, content: <Suspense fallback={<Skeleton />}>{tab.content}</Suspense> }))} /></>;
}

export default function ProjectPage() {
  const { projectId = "" } = useParams();
  const { scope } = useScope();
  const query = useProject(projectId);
  return <section><h1>Проект</h1><QueryView query={query}>{data =>
    scope.workspaceId && data.workspace_id !== scope.workspaceId
      ? <Navigate replace to={`/p/${segment(projectId)}?workspace_id=${segment(data.workspace_id)}`} />
      : <ProjectDetail key={data.project_id} project={data} />}</QueryView></section>;
}
