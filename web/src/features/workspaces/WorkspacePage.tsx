import { hashKey, notifyManager, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useCallback, useState, useSyncExternalStore } from "react";
import { useParams, useSearchParams } from "react-router";
import type { ListProjectsView, WorkspaceView } from "../../api/generated/workspace";
import { EmptyState } from "../../components/data/EmptyState";
import { allowed, segment, useCommand, usePage } from "../../api/hooks/workspace";
import { keys } from "../../api/keys";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { SafeLink } from "../../components/content/SafeLink";
import { KeyValue } from "../../components/data/KeyValue";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { Skeleton } from "../../components/primitives/Skeleton";
import { Tabs } from "../../components/primitives/Tabs";
import { escapeText } from "../../lib/safeText";
import { WorkspaceFiles } from "../files/FilesPage";
import { MembersPanel } from "../access/MembersPanel";
import CreateProjectDialog from "../projects/CreateProjectDialog";
import HostsPage from "../projects/HostsPage";
import WorkspacesPage, { QueryView } from "./WorkspacesPage";

export function ArchiveAction({ path, workspaceId, version }: { path: string; workspaceId: string; version: number }) {
  const [confirmedVersion, setConfirmedVersion] = useState<number | null>(null);
  const action = useCommand(workspaceId);
  return <>
    <Button disabled={action.isPending} onClick={() => setConfirmedVersion(version)}>Архивировать</Button>
    <ConfirmDialog destructive requireReason open={confirmedVersion !== null} title="Архивировать?" onClose={() => setConfirmedVersion(null)}
      onConfirm={reason => {
        if (confirmedVersion !== null) action.mutate({ path, version: confirmedVersion, body: { reason } });
        setConfirmedVersion(null);
      }} />
    {action.error && <ErrorPanel error={action.error} />}
  </>;
}

function Projects({ workspace }: { workspace: WorkspaceView }) {
  const { me } = useAuth();
  const { workspace_id: id } = workspace;
  const { query, cursor } = usePage<ListProjectsView["items"][number]>(
    `/workspaces/${segment(id)}/projects`, [...keys.workspace(id), "projects"],
  );
  return <>
    {workspace.state === "active" && allowed(me, "project.create", workspace.workspace_id) && <CreateProjectDialog workspaceId={workspace.workspace_id} />}
    <QueryView query={query}>{data => <>
      <Table rows={data.items} rowKey={p => p.project_id} empty="Нет проектов" columns={[
        { id: "name", header: "Проект", cell: p => <SafeLink href={`/p/${segment(p.project_id)}`}>{p.title}</SafeLink> },
        { id: "state", header: "Состояние", cell: p => escapeText(p.state) },
      ]} />
      <Pagination next={data.next} {...cursor} />
    </>}</QueryView>
  </>;
}

function WorkspaceDetail({ workspace }: { workspace: WorkspaceView }) {
  const { me } = useAuth();
  const [active, setActive] = useState("projects");
  const id = workspace.workspace_id;
  return <>
    <h2>{escapeText(workspace.title)}</h2>
    <dl><KeyValue label="Состояние" value={workspace.state} /><KeyValue label="Проекты" value={workspace.project_count} /></dl>
    {workspace.state !== "archived" && allowed(me, "workspace.manage", id) &&
      <ArchiveAction path={`/workspaces/${segment(id)}/archive`} workspaceId={id} version={workspace.row_version} />}
    <Tabs active={active} onSelect={setActive} label="Рабочее пространство" tabs={[
      { id: "projects", label: "Проекты", content: <Projects workspace={workspace} /> },
      ...(allowed(me, "workspace.read", id) ? [{ id: "members", label: "Участники", content: active === "members" ? <MembersPanel scopeId={id} ancestors={[id]} /> : null }] : []),
      { id: "files", label: "Файлы", content: <WorkspaceFiles active={workspace.state === "active"} workspaceId={id} projectId={null} /> },
      { id: "hosts", label: "Хосты", content: <HostsPage workspaceId={id} /> },
    ]} />
  </>;
}

// The shell owns both the slug lookup and its cursor-bound workspace snapshot.
// Observe their cache state without replacing their fetch functions.
function useShellQuery<T>(key: QueryKey) {
  const client = useQueryClient();
  const hash = hashKey(key);
  const subscribe = useCallback((onChange: () => void) => {
    const notify = notifyManager.batchCalls(onChange);
    return client.getQueryCache().subscribe(event => {
      if (event.query.queryHash === hash && (event.type === "updated" || event.type === "removed")) notify();
    });
  }, [client, hash]);
  const state = useSyncExternalStore(subscribe, () => client.getQueryState<T>(key));
  return { data: state?.data, error: state?.error };
}

export default function WorkspacePage() {
  const { scope } = useScope();
  const { workspaceSlug } = useParams();
  const [search] = useSearchParams();
  const directory = search.get("view") === "workspaces";
  // Observe the shell's paginated slug resolution, including its terminal error.
  const resolution = useShellQuery(["scope-workspace", scope.projectId, workspaceSlug]);
  const query = useShellQuery<WorkspaceView>([...keys.scope(scope), "workspace-detail"]);
  if (directory) return <WorkspacesPage />;
  const missing = <EmptyState title="Пространство не найдено" />;
  return <section>
    <h1>Рабочее пространство</h1>
    <SafeLink href={`/w/${segment(workspaceSlug ?? "")}?view=workspaces`}>Все пространства</SafeLink>
    {scope.workspaceId ? <QueryView query={query}>{workspace => workspace.slug === workspaceSlug
      ? <WorkspaceDetail key={workspace.workspace_id} workspace={workspace} /> : missing}</QueryView>
      : resolution.error ? <ErrorPanel error={resolution.error} /> : resolution.data === null ? missing : <Skeleton />}
  </section>;
}
