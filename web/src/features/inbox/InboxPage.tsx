import { useEffect, useId, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { decisionStates, field, inboxScopePattern, inboxTarget, record, useExecutionDetail, useInboxRequests, type DecisionRequest } from "../../api/hooks/execution";
import { useProposedIntents } from "../../api/hooks/policy";
import { allowed } from "../../api/hooks/workspace";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { EmptyState } from "../../components/data/EmptyState";
import { Filters } from "../../components/data/Filters";
import { Pagination } from "../../components/data/Pagination";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Spinner } from "../../components/primitives/Spinner";
import { ApprovalCard } from "./ApprovalCard";
import { DeviationCard } from "./DeviationCard";
import { EscalationCard } from "./EscalationCard";
import { ManualCheckCard } from "./ManualCheckCard";
import { InboxRequestCard, QuestionCard } from "./QuestionCard";

const kinds = {
  all: "Все",
  question: "Вопросы",
  approval: "Одобрения",
  manual_check: "Ручные проверки",
  escalation: "Эскалации",
  deviation: "Отклонения",
};
const states = {
  open: "Открытые",
  answered: "С ответом",
  applied: "Применённые",
  assumed: "Принятые как допущение",
  denied: "Отклонённые",
  stale: "Устаревшие",
  expired: "Просроченные",
  cancelled: "Отменённые",
  all: "Все",
};
function ScopeField({ target, onApply }: { target: string; onApply(value: string): void }) {
  const [value, setValue] = useState(target);
  const input = useId();
  return (
    <form onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); onApply(value.trim()); }}>
      <label htmlFor={input}>Область</label>{" "}
      <input id={input} value={value} onChange={event => setValue(event.target.value)}
        pattern={inboxScopePattern} placeholder="project:UUID или run:UUID" />
      {" "}<Button type="submit">Применить область</Button>
    </form>
  );
}

function intentFor(item: DecisionRequest) {
  const payload = record(item.payload);
  const id = payload.intent_id ?? record(payload.refs).intent_id;
  return typeof id === "string" && id !== "" ? id : null;
}

function isDeviation(item: DecisionRequest) {
  return item.kind === "deviation" || (item.kind === "escalation" && record(item.payload).code === "NOT_ACCEPTABLE");
}

function DecisionCard({ item }: { item: DecisionRequest }) {
  const payload = record(item.payload);
  switch (item.kind) {
    case "question": return <QuestionCard item={item} />;
    case "escalation":
    case "budget":
    case "readiness": return <EscalationCard item={item} deviation={isDeviation(item) && <DeviationCard item={item} embedded />} />;
    case "manual_check": return <ManualCheckCard item={item} />;
    case "deviation": return <DeviationCard item={item} />;
  }
  return <InboxRequestCard item={item} title={field(payload.summary ?? payload.code ?? item.kind)} />;
}

function InboxLists({ target, scopeId, kind, state, scopeReady, canListIntents }: {
  target: string | null;
  scopeId: string | null;
  kind: string;
  state: string;
  scopeReady: boolean;
  canListIntents: boolean;
}) {
  const { scope } = useScope();
  const { me } = useAuth();
  const requests = useInboxRequests(target, kind, state, scopeReady);
  const showIntents = canListIntents && allowed(me, "policy.read", scope.workspaceId) && (kind === "all" || kind === "approval");
  const intents = useProposedIntents(scopeId, showIntents);
  const showProposed = showIntents && (state === "open" || state === "all") && scope.workspaceId !== null;
  const decisions = (requests.query.data?.items ?? []).filter(item => kind !== "deviation" || isDeviation(item));
  const approvals = new Map<string, DecisionRequest | undefined>();
  if (showProposed) {
    for (const { intent_id } of intents.query.data?.items ?? []) approvals.set(intent_id, undefined);
  }
  const otherDecisions = decisions.filter(item => {
    const intentId = item.kind === "approval" ? intentFor(item) : null;
    if (!intentId) return true;
    approvals.set(intentId, item);
    return false;
  });
  const approvalsHeading = showProposed ? "Предложенные эффекты" : "Одобрения";

  return (
    <>
      {target !== null && (
        <section aria-label="Запросы решений">
          <h2>Запросы решений</h2>
          {requests.query.isError && <ErrorPanel error={requests.query.error} onRetry={() => { void requests.query.refetch(); }} />}
          {requests.query.isPending && <Spinner />}
          {requests.query.isSuccess && decisions.length === 0 && <EmptyState title="Нет запросов решений" />}
          {otherDecisions.map(item => scopeReady
            ? <DecisionCard key={`${field(item.request_id)}:${field(item.revision)}`} item={item} />
            : <InboxRequestCard key={field(item.request_id)} item={item}
                title={field(record(item.payload).text ?? record(item.payload).check_key ?? item.kind)} />)}
          <Pagination next={requests.query.data?.next_after ?? null} {...requests.cursor} busy={requests.query.isFetching} />
        </section>
      )}
      {(showProposed || approvals.size > 0) && (
        <section aria-label={approvalsHeading}>
          <h2>{approvalsHeading}</h2>
          {showProposed && intents.query.isError && <ErrorPanel error={intents.query.error} onRetry={() => { void intents.query.refetch(); }} />}
          {showProposed && intents.query.isPending && <Spinner />}
          {showProposed && intents.query.isSuccess && approvals.size === 0 && <EmptyState title="Нет предложенных эффектов" />}
          {[...approvals].map(([id, item]) => <ApprovalCard key={id} intentId={id} request={item} />)}
          {showProposed && <Pagination next={intents.query.data?.next_cursor ?? null} {...intents.cursor} busy={intents.query.isFetching} />}
        </section>
      )}
    </>
  );
}

export default function InboxPage() {
  const { scope } = useScope();
  const [params, setParams] = useSearchParams();
  const rawTarget = params.get("scope");
  const target = inboxTarget(rawTarget, scope.projectId);
  const kind = params.get("kind") ?? "all";
  const state = params.get("state") ?? "open";
  const selectedKind = Object.hasOwn(kinds, kind) ? kind : "all";
  const selectedState = state === "all" || decisionStates.some(value => value === state) ? state : "open";
  const [level, id = ""] = target?.split(":") ?? [];
  const runId = level === "run" ? id : "";
  const run = useExecutionDetail("run", runId);
  const project = level === "project" ? id : run.data?.project_id;
  const workspace = run.data?.workspace_id;

  useEffect(() => {
    if (!rawTarget || !project) return;
    if (project === scope.projectId && (!workspace || workspace === scope.workspaceId)) return;
    setParams(current => {
      const next = new URLSearchParams(current);
      next.set("project_id", project);
      if (workspace) next.set("workspace_id", workspace);
      else next.delete("workspace_id");
      return next;
    }, { replace: true });
  }, [rawTarget, project, workspace, scope.projectId, scope.workspaceId, setParams]);

  const ready = target !== null && project === scope.projectId && (!workspace || workspace === scope.workspaceId);
  function update(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next);
  }

  return (
    <section className="section">
      <h1>Входящие</h1>
      <Filters onReset={() => {
        const next = new URLSearchParams(params);
        for (const key of ["kind", "state", "scope"]) next.delete(key);
        setParams(next);
      }}>
        <label>Тип{" "}
          <select value={selectedKind} onChange={event => update("kind", event.target.value)}>
            {Object.entries(kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>{" "}
        <label>Состояние{" "}
          <select value={selectedState} onChange={event => update("state", event.target.value)}>
            {Object.entries(states).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <ScopeField key={rawTarget ?? target} target={rawTarget ?? target ?? ""} onApply={value => update("scope", value)} />
      </Filters>
      {target === null && (rawTarget === null
        ? <p>Выберите проект или укажите область запуска.</p>
        : <p role="alert">Укажите область в формате project:UUID или run:UUID.</p>)}
      {runId && run.isError && <ErrorPanel error={run.error} onRetry={() => { void run.refetch(); }} />}
      <InboxLists key={JSON.stringify([target, selectedKind, selectedState])}
        target={target} scopeId={ready ? id : null} kind={selectedKind}
        state={selectedState} scopeReady={ready} canListIntents={rawTarget === null || ready} />
    </section>
  );
}
