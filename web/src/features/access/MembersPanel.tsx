import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { ListPrincipalsView, MembershipView, Role } from "../../api/generated/access";
import { RoleValues } from "../../api/generated/access";
import { allowed, segment, useCommand, usePage, withParams } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { CopyId } from "../../components/data/CopyId";
import { Pagination } from "../../components/data/Pagination";
import { Table, type Column } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";

const roleLabels: Record<Role, string> = {
  owner: "Владелец",
  maintainer: "Сопровождающий",
  member: "Участник",
  viewer: "Наблюдатель",
  worker: "Воркер",
};

function isRole(value: string): value is Role {
  return (RoleValues as readonly string[]).includes(value);
}

export function MembersPanel({
  scopeId,
  principalId,
  ancestors,
}: {
  scopeId?: string;
  principalId?: string;
  ancestors: readonly (string | null)[];
}) {
  const { me, transport } = useAuth();
  const client = useQueryClient();
  const manageable = allowed(me, "membership.manage", ...ancestors);
  const canPickPrincipal = !principalId && allowed(me, "principal.manage");
  const principalChoices = useQuery({
    queryKey: ["access", "principals", "membership-picker"],
    enabled: canPickPrincipal,
    queryFn: async ({ signal }) => {
      const response = await transport.request<ListPrincipalsView>("GET", "/api/v1/principals?limit=50", { signal });
      return response.data.items;
    },
  });
  const listPath = withParams("/memberships", { scope_id: scopeId, principal_id: principalId });
  const { query, cursor } = usePage<MembershipView>(listPath, ["access", "memberships", scopeId ?? "", principalId ?? ""]);
  const workspaceId = ancestors.find((id) => id && id !== scopeId) ?? scopeId ?? null;
  const command = useCommand(workspaceId, () => { void client.invalidateQueries({ queryKey: ["access"] }); });
  const [principal, setPrincipal] = useState(principalId ?? "");
  const [scope, setScope] = useState(scopeId ?? "");
  const [role, setRole] = useState<Role>("member");

  function grant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextPrincipal = (principalId ?? principal).trim();
    const nextScope = (scopeId ?? scope).trim();
    if (!nextPrincipal || !nextScope) return;
    command.mutate({
      path: "/memberships",
      body: { scope_id: nextScope, principal_id: nextPrincipal, role },
    });
  }

  return <>
    {manageable && <form onSubmit={grant}>
      {canPickPrincipal && <label>Принципал
        <select
          value={principalChoices.data?.some((item) => item.principal_id === principal) ? principal : ""}
          onChange={(event) => setPrincipal(event.target.value)}
        >
          <option value="">{principalChoices.isPending ? "Загрузка…" : "Выберите принципала"}</option>
          {principalChoices.data?.map((item) => (
            <option key={item.principal_id} value={item.principal_id}>
              {escapeText(`${item.display_name} · ${item.principal_id}`)}
            </option>
          ))}
        </select>
      </label>}
      {!principalId && <label>Идентификатор принципала
        <input value={principal} onChange={(event) => setPrincipal(event.target.value)} autoComplete="off" />
      </label>}
      {!scopeId && <label>Идентификатор области
        <input value={scope} onChange={(event) => setScope(event.target.value)} autoComplete="off" />
      </label>}
      <label>Роль
        <select value={role} onChange={(event) => { if (isRole(event.target.value)) setRole(event.target.value); }}>
          {RoleValues.map((value) => <option key={value} value={value}>{roleLabels[value]}</option>)}
        </select>
      </label>
      <Button type="submit" disabled={command.isPending}>Назначить роль</Button>
    </form>}
    <QueryView query={query}>{page => {
      const items = Array.isArray(page.items) ? page.items : [];
      const columns: Column<MembershipView>[] = [
        { id: "name", header: "Участник", cell: (row) => escapeText(row.display_name) },
        { id: "principal", header: "Идентификатор принципала", cell: (row) => <CopyId id={row.principal_id} /> },
        { id: "scope", header: "Область", cell: (row) => escapeText(`${row.scope_kind} ${row.scope_id}`) },
        { id: "role", header: "Роль", cell: (row) => manageable
          ? <select aria-label={`Роль ${row.display_name}`} value={row.role} onChange={(event) => {
            if (!isRole(event.target.value) || event.target.value === row.role) return;
            command.mutate({
              path: "/memberships",
              body: { scope_id: row.scope_id, principal_id: row.principal_id, role: event.target.value },
            });
          }}>{RoleValues.map((value) => <option key={value} value={value}>{roleLabels[value]}</option>)}</select>
          : escapeText(roleLabels[row.role]) },
        { id: "revoke", header: "Действия", cell: (row) => manageable
          ? <Button disabled={command.isPending} onClick={() => command.mutate({
            method: "DELETE",
            path: `/memberships/${segment(row.scope_id)}/${segment(row.principal_id)}`,
          })}>Отозвать</Button>
          : null },
      ];
      return <>
        <Table rows={items} rowKey={(row) => `${row.scope_id}:${row.principal_id}`} empty="Нет участников" columns={columns} />
        <Pagination {...cursor} next={page.next ?? null} />
      </>;
    }}</QueryView>
    {command.error && <ErrorPanel error={command.error} />}
  </>;
}
