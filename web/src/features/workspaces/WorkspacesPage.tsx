import { useState, type ReactNode } from "react";
import type { WorkspaceSummaryView } from "../../api/generated/workspace";
import { allowed, segment, usePage, withParams, workspacesKey } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { SafeLink } from "../../components/content/SafeLink";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Skeleton } from "../../components/primitives/Skeleton";
import { escapeText } from "../../lib/safeText";
import CreateWorkspaceDialog from "./CreateWorkspaceDialog";

export function QueryView<T>({ query, children }: {
  query: { data: T | undefined; error: unknown };
  children(data: T): ReactNode;
}) {
  if (query.error) return <ErrorPanel error={query.error} />;
  if (query.data === undefined) return <Skeleton />;
  return <>{children(query.data)}</>;
}

export default function WorkspacesPage() {
  const { me } = useAuth();
  const [state, setState] = useState("");
  const { query, cursor } = usePage<WorkspaceSummaryView>(withParams("/workspaces", { state }), workspacesKey);
  return <section>
    <h1>Рабочие пространства</h1>
    {allowed(me, "workspace.create") && <CreateWorkspaceDialog />}
    <label>Состояние пространства<select value={state} onChange={e => setState(e.target.value)}>
      <option value="">Все</option>{["active", "suspended", "archived"].map(s => <option key={s}>{s}</option>)}
    </select></label>
    <QueryView query={query}>{page => <>
      <Table rows={page.items} rowKey={row => row.workspace_id} empty="Нет рабочих пространств" columns={[
        { id: "name", header: "Название", cell: row => <SafeLink href={withParams(`/w/${segment(row.slug)}`, { workspace_id: row.workspace_id })}>{row.title}</SafeLink> },
        { id: "state", header: "Состояние", cell: row => escapeText(row.state) },
      ]} />
      <Pagination next={page.next} {...cursor} />
    </>}</QueryView>
  </section>;
}
