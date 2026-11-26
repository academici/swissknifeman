import { useState, type FormEvent } from "react";
import type { CheckoutLocationView, ListProjectRepositoriesView, ProjectView, RepositoryView } from "../../api/generated/workspace";
import { allowed, segment, useCommand, usePage, useRead, withParams } from "../../api/hooks/workspace";
import { keys } from "../../api/keys";
import { useAuth } from "../../app/providers/AuthProvider";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";

function fields(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return new FormData(event.currentTarget);
}

export default function ProjectReposTab({ project }: { project: ProjectView }) {
  const { me } = useAuth();
  const { workspace_id: ws, project_id: id } = project;
  const [host, setHost] = useState("");
  const [lookup, setLookup] = useState<string | null>(null);
  const [detach, setDetach] = useState<string | null>(null);
  const [selected, setSelected] = useState<RepositoryView | null>(null);
  const mountsPath = `/projects/${segment(id)}/repositories`;
  const reposPath = `/workspaces/${segment(ws)}/repositories`;
  const mounts = useRead<ListProjectRepositoriesView>(keys.workspace(ws), withParams(mountsPath, { host_id: host }));
  const canLocate = allowed(me, "checkout.read_locator", id, ws);
  const checkout = useRead<CheckoutLocationView>(keys.workspace(ws), withParams(`/projects/${segment(id)}/checkout`, {
    host_id: host, mount_name: lookup,
  }), canLocate && !!host && lookup !== null);
  const repos = usePage<RepositoryView>(reposPath);
  const action = useCommand(ws, () => setSelected(null));
  const manageProject = project.state === "active" && allowed(me, "project.manage", id, ws);
  const manageRepos = allowed(me, "repo.manage", ws);
  return <section>
    <h2>Репозитории проекта</h2>
    <form onSubmit={e => { setHost(String(fields(e).get("host")).trim()); setLookup(null); }}>
      <label>ID хоста<input name="host" /></label><Button type="submit">Показать привязки</Button>
    </form>
    <QueryView query={mounts}>{page => <Table rows={page.items} rowKey={row => row.mount_name} empty="Нет подключённых репозиториев" columns={[
      { id: "mount", header: "Точка подключения", cell: row => escapeText(row.mount_name) },
      { id: "repo", header: "Репозиторий", cell: row => escapeText(row.repository.title) },
      { id: "role", header: "Роль", cell: row => escapeText(row.role) },
      { id: "binding", header: "Привязка", cell: ({ binding, mount_name }) => binding ? <>
        {escapeText(binding.state)}{binding.is_stale && " · Устарела"}
        {typeof binding.local_locator === "string" && <p><code>{escapeText(binding.local_locator)}</code></p>}
        {canLocate && host && <Button onClick={() => setLookup(mount_name)}>Проверить расположение</Button>}
      </> : "Нет привязки" },
      ...(manageProject ? [{ id: "detach", header: "Действия", cell: (row: ListProjectRepositoriesView["items"][number]) =>
        <Button disabled={action.isPending} onClick={() => setDetach(row.mount_name)}>Отключить</Button> }] : []),
    ]} />}</QueryView>
    {canLocate && lookup && <QueryView query={checkout}>{location => <p>
      {escapeText(location.state)} {location.local_locator && <code>{escapeText(location.local_locator)}</code>}
    </p>}</QueryView>}
    <ConfirmDialog open={detach !== null} title={`Отключить ${detach ?? ""}?`} destructive onClose={() => setDetach(null)}
      onConfirm={() => {
        if (detach !== null) action.mutate({ method: "DELETE", path: mountsPath + "/" + segment(detach) });
        setDetach(null);
      }} />
    <h2>Репозитории пространства</h2>
    <QueryView query={repos.query}>{page => <>
      <Table rows={page.items} rowKey={row => row.repository_id} empty="Нет репозиториев" columns={[
        { id: "name", header: "Название", cell: row => escapeText(row.title) },
        { id: "remote", header: "Remote", cell: row => escapeText(row.canonical_remote ?? "—") },
        ...(manageProject || manageRepos ? [{ id: "select", header: "Действия", cell: (row: RepositoryView) =>
          <Button onClick={() => setSelected(row)}>Выбрать {escapeText(row.title)}</Button> }] : []),
      ]} /><Pagination {...repos.cursor} next={page.next} />
    </>}</QueryView>
    {selected && <section>
      <h3>{escapeText(selected.title)}</h3>
      {manageProject && <form onSubmit={e => {
        const data = fields(e);
        action.mutate({ path: mountsPath, body: { repository_id: selected.repository_id, mount_name: data.get("mount"), role: data.get("role") } });
      }}>
        <label>Точка подключения<input name="mount" defaultValue="main" required /></label>
        <label>Роль<select name="role">{["primary", "secondary", "docs", "infra"].map(role => <option key={role}>{role}</option>)}</select></label>
        <Button type="submit" disabled={action.isPending}>Подключить репозиторий</Button>
      </form>}
      {manageRepos && <form onSubmit={e => {
        const data = fields(e);
        action.mutate({ path: `/repositories/${segment(selected.repository_id)}/remotes`, body: { url: data.get("url"), make_primary: data.has("primary") } });
      }}>
        <label>Новый remote<input name="url" required /></label><label><input name="primary" type="checkbox" />Основной remote</label>
        <Button type="submit" disabled={action.isPending}>Добавить remote</Button>
      </form>}
    </section>}
    {manageRepos && <form onSubmit={e => {
      const data = fields(e);
      action.mutate({ path: reposPath, body: { title: data.get("title"), remote_url: data.get("remote") || null, external_id: null } });
    }}>
      <label>Название репозитория<input name="title" required maxLength={200} /></label>
      <label>Remote URL<input name="remote" /></label>
      <Button type="submit" disabled={action.isPending}>Зарегистрировать репозиторий</Button>
    </form>}
    {action.error && <ErrorPanel error={action.error} />}
  </section>;
}
