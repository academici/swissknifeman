import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { CreatePrincipalResult, ListPrincipalsView, PrincipalKind, PrincipalView } from "../../api/generated/access";
import { PrincipalKindValues } from "../../api/generated/access";
import { newKey } from "../../api/idempotency";
import { allowed, segment, usePage, versionTag, withParams } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { CopyId } from "../../components/data/CopyId";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { escapeText } from "../../lib/safeText";
import { QueryView } from "../workspaces/WorkspacesPage";
import { MembersPanel } from "./MembersPanel";

const kindLabels: Record<PrincipalKind, string> = {
  human: "Человек",
  service: "Сервис",
  worker: "Воркер",
};

function isKind(value: string): value is PrincipalKind {
  return (PrincipalKindValues as readonly string[]).includes(value);
}

export default function PrincipalsPage() {
  const { me, transport } = useAuth();
  const client = useQueryClient();
  const canManage = allowed(me, "principal.manage");
  const [kind, setKind] = useState<PrincipalKind | "">("");
  const [selected, setSelected] = useState<string | null>(null);
  const [disableId, setDisableId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const { query, cursor } = usePage<ListPrincipalsView["items"][number]>(
    withParams("/principals", { kind: kind || undefined }),
    ["access", "principals", kind],
  );

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const displayName = String(data.get("display_name") ?? "").trim();
    const nextKind = String(data.get("kind") ?? "");
    const issuer = String(data.get("issuer") ?? "").trim();
    const subject = String(data.get("subject") ?? "").trim();
    if (!displayName || !isKind(nextKind)) return;
    setPending(true);
    setError(null);
    setCreatedId(null);
    try {
      const created = await transport.request<CreatePrincipalResult>("POST", "/api/v1/principals", {
        idempotencyKey: newKey(),
        body: {
          kind: nextKind,
          display_name: displayName,
          ...(issuer && subject ? { identity: { issuer, subject } } : {}),
        },
      });
      setCreatedId(created.data.principal_id);
      form.reset();
      await client.invalidateQueries({ queryKey: ["access", "principals"] });
    } catch (failure) {
      setError(failure);
    } finally {
      setPending(false);
    }
  }

  async function disable(reason: string) {
    if (!disableId || !reason.trim()) return;
    const id = disableId;
    setDisableId(null);
    setPending(true);
    setError(null);
    try {
      const detail = await transport.request<PrincipalView>("GET", `/api/v1/principals/${segment(id)}`);
      await transport.request("POST", `/api/v1/principals/${segment(id)}/disable`, {
        idempotencyKey: newKey(),
        ifMatch: detail.etag ?? versionTag(detail.data.row_version),
        body: { reason },
      });
      await client.invalidateQueries({ queryKey: ["access", "principals"] });
    } catch (failure) {
      setError(failure);
    } finally {
      setPending(false);
    }
  }

  return <section>
    <h1>Принципалы</h1>
    <label>Вид
      <select value={kind} onChange={(event) => { if (event.target.value === "" || isKind(event.target.value)) setKind(event.target.value); }}>
        <option value="">Все</option>
        {PrincipalKindValues.map((value) => <option key={value} value={value}>{kindLabels[value]}</option>)}
      </select>
    </label>
    {canManage && <form onSubmit={(event) => { void create(event); }}>
      <label>Отображаемое имя<input name="display_name" required autoComplete="off" /></label>
      <label>Вид нового принципала
        <select name="kind" defaultValue="human">
          {PrincipalKindValues.map((value) => <option key={value} value={value}>{kindLabels[value]}</option>)}
        </select>
      </label>
      <label>Издатель удостоверения<input name="issuer" autoComplete="off" /></label>
      <label>Субъект удостоверения<input name="subject" autoComplete="off" /></label>
      <Button type="submit" disabled={pending}>Создать принципала</Button>
    </form>}
    {createdId && <p role="status">Создан принципал <CopyId id={createdId} /></p>}
    <QueryView query={query}>{page => {
      const items = Array.isArray(page.items) ? page.items as readonly ListPrincipalsView["items"][number][] : [];
      return <>
        <Table rows={items} rowKey={(row) => row.principal_id} empty="Нет принципалов" columns={[
          { id: "name", header: "Имя", cell: (row) => escapeText(row.display_name) },
          { id: "id", header: "Идентификатор", cell: (row) => <CopyId id={row.principal_id} /> },
          { id: "kind", header: "Вид", cell: (row) => escapeText(kindLabels[row.kind]) },
          { id: "state", header: "Состояние", cell: (row) => escapeText(row.state) },
          { id: "actions", header: "Действия", cell: (row) => <>
            <Button onClick={() => setSelected(row.principal_id)}>Роли</Button>
            {canManage && row.state === "active" &&
              <Button disabled={pending} onClick={() => setDisableId(row.principal_id)}>Отключить</Button>}
          </> },
        ]} />
        <Pagination {...cursor} next={page.next ?? null} />
      </>;
    }}</QueryView>
    {selected && <>
      <h2>Роли принципала</h2>
      <MembersPanel principalId={selected} ancestors={[]} />
    </>}
    <ConfirmDialog destructive requireReason open={disableId !== null} title="Отключить принципала?"
      onClose={() => setDisableId(null)} onConfirm={(reason) => { void disable(reason); }} />
    {error != null && <ErrorPanel error={error} />}
  </section>;
}
