import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { CreateToken, CreateTokenResult, TokenSummaryView } from "../../api/generated/access";
import type { Uuid } from "../../api/generated/kernel";
import type { ExchangePairingToken, WorkspaceSummaryView } from "../../api/generated/workspace";
import { newKey } from "../../api/idempotency";
import { allowed, operatorError, segment, usePage } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";
import { Skeleton } from "../../components/primitives/Skeleton";
import { copyText } from "../../lib/clipboard";
import { escapeText } from "../../lib/safeText";
import { TokenGrants, type ProjectGrant } from "./TokenGrants";

const tokensKey = ["access", "tokens"] as const;
type Pairing = ExchangePairingToken & { expires_at: string };
type Issued = { kind: "personal"; token: CreateTokenResult } | { kind: "pairing"; pairing: Pairing };

function OneTimeCredential({ issued, dismiss }: { issued: Issued; dismiss(): void }) {
  const [copyStatus, setCopyStatus] = useState("");
  const pairing = issued.kind === "pairing" ? issued.pairing : undefined;
  const value = issued.kind === "personal" ? issued.token.secret : issued.pairing.pairing_secret;
  const expires = issued.kind === "personal" ? issued.token.expires_at : issued.pairing.expires_at;
  const payload: ExchangePairingToken | undefined = pairing && {
    workspace_id: pairing.workspace_id, pairing_id: pairing.pairing_id, pairing_secret: pairing.pairing_secret,
  };
  async function copy(text: string) {
    try {
      await copyText(text);
      setCopyStatus("Скопировано");
    } catch {
      setCopyStatus("Не удалось скопировать. Выделите и скопируйте значение вручную.");
    }
  }
  return <Dialog open onClose={dismiss} title={pairing ? "Одноразовый код сопряжения" : "Секрет токена"}>
    <p>Скопируйте значение перед закрытием окна. Оно показывается один раз.</p>
    <label>{pairing ? "Код сопряжения" : "Секрет токена"}
      <input readOnly autoComplete="off" spellCheck={false} value={value} onFocus={event => event.currentTarget.select()} />
    </label>
    <Button onClick={() => void copy(value)}>{pairing ? "Копировать код" : "Копировать секрет"}</Button>
    {expires && <p>Действует до <time dateTime={expires}>{escapeText(expires)}</time></p>}
    {pairing && payload && <>
      <h3>Обмен кода</h3>
      <ol>
        <li>На стороне получателя отправьте JSON методом <code>POST</code> на
          {" "}<code>/api/v1/auth/pairing/exchange</code> этого экземпляра SKM.
          Укажите <code>Content-Type: application/json</code>.</li>
        <li>Сохраните <code>token_secret</code> из ответа. Используйте его для входа или как Bearer-токен.</li>
      </ol>
      <p>ID пространства <code>{escapeText(pairing.workspace_id)}</code> · ID сопряжения <code>{escapeText(pairing.pairing_id)}</code></p>
      <Button onClick={() => void copy(JSON.stringify(payload, null, 2))}>Копировать JSON для обмена</Button>
    </>}
    <p role="status">{copyStatus}</p>
  </Dialog>;
}

function TokenBuilder({ principalId }: { principalId: Uuid }) {
  const { transport } = useAuth();
  const client = useQueryClient();
  const [kind, setKind] = useState<Issued["kind"]>("personal");
  const [workspace, setWorkspace] = useState<WorkspaceSummaryView>();
  const [grants, setGrants] = useState<readonly ProjectGrant[]>([]);
  const [issued, setIssued] = useState<Issued>();
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<unknown>();
  const ready = grants.length > 0 && grants.every(g => g.permissions.length > 0);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || pending || issued) return;
    const form = event.currentTarget;
    const fields = new FormData(form);
    const scopeGrants = grants.map(({ project, permissions }) => ({ scope_id: project.project_id, permissions }));
    setFailure(undefined);
    setPending(true);
    // Secret-returning commands run once and keep the response in this component only.
    try {
      if (kind === "pairing" && workspace) {
        const { data } = await transport.request<Pairing>("POST", "/api/v1/auth/pairing", { body: {
          workspace_id: workspace.workspace_id, principal_id: principalId,
          ttl_seconds: Number(fields.get("ttl_seconds")),
          scope_grants: Object.fromEntries(scopeGrants.map(g => [g.scope_id, g.permissions])),
        } });
        setIssued({ kind, pairing: data });
      } else if (kind === "personal") {
        const body: CreateToken = { name: String(fields.get("name")).trim(), scope_grants: scopeGrants };
        if (!body.name) return;
        const { data } = await transport.request<CreateTokenResult>("POST", "/api/v1/tokens", { body });
        setIssued({ kind, token: data });
        void client.invalidateQueries({ queryKey: tokensKey });
      }
    } catch (error) {
      setFailure(operatorError(error));
    } finally {
      setPending(false);
    }
  }

  return <section>
    <h2>Создание токена</h2>
    <form onSubmit={event => void create(event)}>
      <fieldset disabled={pending || Boolean(issued)}>
        <label>Способ выдачи<select value={kind} onChange={event => {
          const next = event.currentTarget.value === "pairing" ? "pairing" : "personal";
          setKind(next);
          setFailure(undefined);
          if (next === "pairing") setGrants(grants.filter(g => g.workspaceId === workspace?.workspace_id));
        }}>
          <option value="personal">Создать токен доступа</option>
          <option value="pairing">Сопряжение по одноразовому коду</option>
        </select></label>
        {kind === "personal" ? <label key="personal">Название токена
          <input name="name" required maxLength={100} pattern="[A-Za-z0-9 ._\-]+" autoComplete="off" />
        </label> : <label key="pairing">Срок действия кода (секунды)
          <input name="ttl_seconds" type="number" min={1} max={3600} step={1} defaultValue={900} required />
        </label>}
        <TokenGrants workspace={workspace} onWorkspace={next => {
          setWorkspace(next);
          if (kind === "pairing") setGrants(grants.filter(g => g.workspaceId === next?.workspace_id));
        }} grants={grants} onGrants={setGrants} />
        <Button type="submit" disabled={!ready || (kind === "pairing" && !workspace) || pending || Boolean(issued)}>
          {kind === "personal" ? "Создать токен" : "Создать код сопряжения"}
        </Button>
      </fieldset>
    </form>
    {pending && <p role="status">Создание…</p>}
    {failure != null && <ErrorPanel error={failure} />}
    {issued && <OneTimeCredential issued={issued} dismiss={() => setIssued(undefined)} />}
  </section>;
}

function ActiveTokens() {
  const { me, transport } = useAuth();
  const client = useQueryClient();
  const { query, cursor } = usePage<TokenSummaryView>("/tokens?include_inactive=false", tokensKey, true);
  const [target, setTarget] = useState<TokenSummaryView>();
  const [revoking, setRevoking] = useState(false);
  const [failure, setFailure] = useState<unknown>();
  async function revoke() {
    if (!target || revoking) return;
    setRevoking(true);
    setFailure(undefined);
    try {
      await transport.request("POST", `/api/v1/tokens/${segment(target.token_id)}/revoke`, { idempotencyKey: newKey() });
      setTarget(undefined);
      await client.invalidateQueries({ queryKey: tokensKey });
    } catch (error) {
      setFailure(operatorError(error));
    } finally {
      setRevoking(false);
    }
  }
  return <section>
    <h2>Активные токены</h2>
    <p>Здесь появляются токены, выданные при обмене кода. Неиспользованные коды действуют до истечения срока.</p>
    <Button onClick={() => void query.refetch()} disabled={query.isFetching}>Обновить список</Button>
    {query.isError && <ErrorPanel error={operatorError(query.error)} onRetry={() => void query.refetch()} />}
    {query.isPending && <Skeleton />}
    {query.data && <>
      <Table rows={query.data.items.filter(t => t.state === "active")} rowKey={t => t.token_id} empty="Нет активных токенов" columns={[
        { id: "name", header: "Токен", cell: t => <>{escapeText(t.name)} · <code>{escapeText(t.prefix)}</code></> },
        { id: "grants", header: "Разрешения", cell: t => t.scope_grants
          ? <ul>{t.scope_grants.map(g => <li key={g.scope_id}>
            <code>{escapeText(g.scope_id)}</code> · {escapeText(g.permissions.join(", "))}
          </li>)}</ul>
          : escapeText(t.permissions?.join(", ") ?? "—") },
        { id: "expiry", header: "Действует до", cell: t => t.expires_at ? <time dateTime={t.expires_at}>{escapeText(t.expires_at)}</time> : "—" },
        { id: "action", header: "Действие", cell: t => <Button disabled={revoking} onClick={() => {
          setFailure(undefined);
          setTarget(t);
        }}>Отозвать {escapeText(t.name)}</Button> },
      ]} />
      <Pagination {...cursor} next={query.data.next} />
    </>}
    {target && <Dialog open title="Отзыв токена" onClose={() => { if (!revoking) setTarget(undefined); }}>
      <p>Отозвать токен {escapeText(target.name)} ({escapeText(target.prefix)})?</p>
      {target.token_id === me?.token?.token_id && <p>Это завершит текущий сеанс.</p>}
      {failure != null && <ErrorPanel error={failure} />}
      <Button disabled={revoking} onClick={() => void revoke()}>Подтвердить отзыв</Button>
    </Dialog>}
  </section>;
}

export default function TokensPage() {
  const { me, sessionGeneration } = useAuth();
  return <section>
    <h1>Токены доступа</h1>
    {!me || !allowed(me, "token.own") ? <p role="alert">Нет доступа к управлению токенами.</p> :
      <div key={`${me.principal.principal_id}:${sessionGeneration}`}>
        {me.principal.kind !== "worker" && <TokenBuilder principalId={me.principal.principal_id} />}
        <ActiveTokens />
      </div>}
  </section>;
}
