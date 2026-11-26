import { useId, useState, type FormEvent, type ReactNode } from "react";
import type { AnswerDecisionRequestDefsJsonValue } from "../../api/generated/execution_02";
import type { Uuid } from "../../api/generated/kernel";
import { field, record, useAnswerDecision, useExecutionDetail, useInboxPermissions, type DecisionRequest } from "../../api/hooks/execution";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { DataList } from "../../components/data/DataList";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";

export function InboxRequestCard({ item, title, children }: { item: DecisionRequest; title: string; children?: ReactNode }) {
  const heading = useId();
  return (
    <article aria-labelledby={heading}>
      <h3 id={heading}>{escapeText(title)}</h3>
      <RequestMetadata item={item} />
      {children}
    </article>
  );
}

export function RequestMetadata({ item }: { item: DecisionRequest }) {
  const payload = record(item.payload);
  const role = item.kind === "manual_check" ? payload.actor_role : resolverRole(item);
  const authority = item.authority ?? payload.authority ?? item.audience;
  return (
    <DataList>
      <KeyValue label="Состояние" value={<StatusBadge status={field(item.state)} />} />
      <KeyValue label="Запуск" value={field(item.run_id)} />
      {item.task_display_key != null && <KeyValue label="Задача" value={field(item.task_display_key)} />}
      <KeyValue label="Роль для ответа" value={field(role, "—")} />
      <KeyValue label="Полномочия" value={field(record(authority).mode ?? authority, "—")} />
      <KeyValue label="Крайний срок" value={field(item.deadline_at, "—")} />
    </DataList>
  );
}

const roleOrder = ["viewer", "member", "maintainer", "owner"];

export function resolverRole(item: DecisionRequest) {
  return item.resolver_role ?? record(item.blocking_reason).resolver_role;
}

export function useRequestAction(item: DecisionRequest, permission: string, requiredRole: unknown) {
  const { me } = useAuth();
  const { scope } = useScope();
  const runId = typeof item.run_id === "string" ? item.run_id : null;
  const allowed = useInboxPermissions(item.state === "open" ? runId : null);
  const minimum = typeof requiredRole === "string" ? roleOrder.indexOf(requiredRole) : -1;
  const candidates = minimum < 0 ? [] : me?.memberships.filter(m => roleOrder.indexOf(m.role) >= minimum) ?? [];
  const scopes = [runId, item.plan_id, scope.projectId, scope.workspaceId];
  const directRole = candidates.some(m => m.scope_kind === "instance" || scopes.includes(m.scope_id));
  const planRoles = candidates.filter(m => m.scope_kind === "plan");
  const detail = useExecutionDetail("run", item.state === "open" && !directRole && planRoles.length ? runId ?? "" : "");
  const hasRole = directRole || planRoles.some(m => m.scope_id === detail.data?.plan_id);
  return (right = permission) => item.state === "open" && hasRole && allowed(right);
}

const runControlOptions = new Set(["raise_budget", "resume_run", "cancel_run", "skip", "new_attempt", "retry_stage", "fail"]);
const deviationOptions = new Set(["accept_deviation", "accept_rejection"]);
const sha = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/u;

export function AnswerForm({ item, escalation = false }: { item: DecisionRequest; escalation?: boolean }) {
  const payload = record(item.payload);
  const can = useRequestAction(item, "inbox.answer", resolverRole(item));
  const mutation = useAnswerDecision(field(item.run_id, ""), field(item.request_id, ""));
  const id = useId();
  const [selected, setSelected] = useState("");
  const [text, setText] = useState("");
  const [rationale, setRationale] = useState("");
  const [json, setJson] = useState("");
  const [commits, setCommits] = useState<Record<string, string>>({});
  if (!can() || (item.audience != null && item.audience !== "owner") || mutation.status === "success" ||
    typeof item.request_id !== "string" || typeof item.revision !== "number") return null;

  const options = Array.isArray(payload.options) ? payload.options.flatMap(value => {
    const option = record(value);
    const key = typeof value === "string" ? value : option.id;
    return typeof key === "string" && key ? [{ key, label: field(option.label ?? option.text, key) }] : [];
  }) : [];
  const canSelect = (key: string) => (!escalation || !runControlOptions.has(key) || can("run.control")) &&
    (!escalation || !deviationOptions.has(key) || can("deviation.accept"));
  const choices = options.filter(({ key }) => canSelect(key));
  if (options.length > 0 && choices.length === 0 && !mutation.awaitsResult) return null;
  const requiresCommits = payload.code === "INTEGRATION_RECHECK_FAILED" && selected === "retry_stage";
  const allMounts = payload.mounts;
  const mounts = Array.isArray(allMounts) && allMounts.every(mount => typeof mount === "string" && mount.length > 0)
    ? [...new Set<string>(allMounts)] : [];
  const approvedCommits = mounts.map(mount => [mount, commits[mount]?.trim() ?? ""] as const);
  const commitsComplete = mounts.length > 0 && approvedCommits.every(([, commit]) => sha.test(commit));
  const requiresJson = !requiresCommits && (payload.answer_schema != null || selected === "raise_budget");
  let value: AnswerDecisionRequestDefsJsonValue | undefined;
  if (requiresCommits && commitsComplete) {
    value = { recheck_commits: Object.fromEntries(approvedCommits) };
  } else if (requiresJson && json.trim()) {
    try { value = JSON.parse(json) as AnswerDecisionRequestDefsJsonValue; }
    catch { /* A partially edited JSON value cannot be submitted. */ }
  }
  const valid = (options.length ? choices.some(option => option.key === selected) :
    text.trim() !== "" || value !== undefined) && ((!requiresCommits && !requiresJson) || value !== undefined);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid || mutation.status !== "idle" || typeof item.revision !== "number") return;
    mutation.answer({
      request_id: item.request_id as Uuid,
      expected_revision: item.revision,
      answer: {
        ...(selected && { option_id: selected }),
        ...(text.trim() && { text: text.trim() }),
        ...(value !== undefined && { value }),
      },
      ...(rationale.trim() && { rationale: rationale.trim() }),
    });
  }

  return (
    <form onSubmit={submit}>
      <fieldset disabled={mutation.status !== "idle"}>
        <legend>Ответ</legend>
        {options.length > 0 && <div>
          <label htmlFor={id + "-option"}>Вариант</label>{" "}
          <select id={id + "-option"} value={selected} onChange={event => setSelected(event.target.value)} required>
            <option value="">Выберите вариант</option>
            {choices.map(({ key, label }) => <option key={key} value={key}>{escapeText(label)}</option>)}
          </select>
        </div>}
        {requiresCommits && <fieldset>
          <legend>Одобренные коммиты</legend>
          {mounts.length === 0 && <p role="alert">Сервер не указал список точек монтирования.</p>}
          {mounts.map((mount, index) => <div key={mount}>
            <label htmlFor={`${id}-mount-${index}`}>SHA для {escapeText(mount)}</label>{" "}
            <input id={`${id}-mount-${index}`} value={Object.hasOwn(commits, mount) ? commits[mount] : ""}
              onChange={event => setCommits({ ...commits, [mount]: event.target.value })}
              spellCheck={false} required />
          </div>)}
        </fieldset>}
        {requiresJson && <div>
          {payload.answer_schema != null && <JsonView value={payload.answer_schema} />}
          <label htmlFor={id + "-value"}>Значение ответа (JSON)</label>{" "}
          <textarea id={id + "-value"} value={json} onChange={event => setJson(event.target.value)} required />
          {json.trim() && value === undefined && <p role="alert">Введите корректное значение JSON.</p>}
        </div>}
        <div>
          <label htmlFor={id + "-text"}>Текст ответа</label>{" "}
          <textarea id={id + "-text"} value={text} onChange={event => setText(event.target.value)} />
        </div>
        <div>
          <label htmlFor={id + "-rationale"}>Обоснование</label>{" "}
          <textarea id={id + "-rationale"} value={rationale} onChange={event => setRationale(event.target.value)} maxLength={2000} />
        </div>
        <Button type="submit" disabled={!valid}>Ответить</Button>
      </fieldset>
      {mutation.error && <ErrorPanel error={mutation.error}
        {...(mutation.awaitsResult ? { onRetry: mutation.retry } : {})} />}
      {mutation.error && !mutation.awaitsResult && <Button onClick={mutation.reset}>Изменить ответ</Button>}
    </form>
  );
}

export function QuestionCard({ item }: { item: DecisionRequest }) {
  const payload = record(item.payload);
  const title = field(payload.text ?? payload.question ?? item.summary, "Вопрос");
  return <InboxRequestCard item={item} title={title}>
    {typeof payload.why_blocked === "string" && <p>{escapeText(payload.why_blocked)}</p>}
    <AnswerForm item={item} />
  </InboxRequestCard>;
}
