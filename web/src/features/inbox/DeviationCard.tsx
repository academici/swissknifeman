import { useId, useState, type FormEvent } from "react";
import { ApiError } from "../../api/errors";
import type { AcceptDeviation } from "../../api/generated/execution_01";
import type { Uuid } from "../../api/generated/kernel";
import { field, record, useAcceptDeviation, type DecisionRequest } from "../../api/hooks/execution";
import { KeyValue } from "../../components/data/KeyValue";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";
import { InboxRequestCard, resolverRole, useRequestAction } from "./QuestionCard";

const scopes: Record<AcceptDeviation["scope"], string> = {
  criterion: "Критерий",
  finding: "Замечание",
  attention_verdict: "Вердикт «требует внимания»",
  coverage: "Покрытие",
};

function DeviationForm({ item }: { item: DecisionRequest }) {
  const can = useRequestAction(item, "deviation.accept", resolverRole(item));
  const mutation = useAcceptDeviation(field(item.run_id, ""), field(item.request_id, ""));
  const payload = record(item.payload);
  const refs = record(payload.refs);
  const criterionId = payload.criterion_id ?? refs.criterion_id;
  const findingId = payload.finding_id ?? refs.finding_id;
  const findingIds = Array.isArray(refs.finding_ids)
    ? [...new Set(refs.finding_ids.filter((id): id is string => typeof id === "string" && id !== ""))]
    : [];
  const payloadScope = payload.scope as AcceptDeviation["scope"];
  const [scope, setScope] = useState<AcceptDeviation["scope"]>(
    Object.hasOwn(scopes, payloadScope) ? payloadScope
      : findingIds.length > 0 || findingId ? "finding" : criterionId ? "criterion" : "attention_verdict",
  );
  const [targetInput, setTargetInput] = useState("");
  const [selectedFinding, setSelectedFinding] = useState(findingIds[0] ?? "");
  const [reason, setReason] = useState("");
  const id = useId();
  if (!can() || typeof item.task_id !== "string" || !item.task_id || mutation.status === "success") return null;

  const needsTarget = scope !== "attention_verdict";
  const chooseFinding = scope === "finding" && findingIds.length > 0;
  const bound = scope === "finding" ? findingId : criterionId;
  const boundTarget = typeof bound === "string" && bound ? bound : null;
  const target = chooseFinding ? (findingIds.includes(selectedFinding) ? selectedFinding : "") : boundTarget ?? targetInput.trim();
  const targetLabel = scope === "finding" ? "ID замечания" : "ID критерия";
  const valid = (!needsTarget || target !== "") && reason.trim() !== "";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.status !== "idle" || !valid) return;
    mutation.accept({
      task_id: item.task_id as Uuid,
      scope,
      ...(scope === "finding" && { finding_id: target as Uuid }),
      ...((scope === "criterion" || scope === "coverage") && { criterion_id: target as Uuid }),
      reason: reason.trim(),
    });
  }

  return <form onSubmit={submit}>
    <fieldset disabled={mutation.status !== "idle"}>
      <legend>Допустить отклонение</legend>
      <label htmlFor={id + "-scope"}>Тип отклонения</label>{" "}
      <select id={id + "-scope"} value={scope} onChange={event => {
        setScope(event.target.value as AcceptDeviation["scope"]);
        setTargetInput("");
      }}>
        {Object.entries(scopes).map(([value, caption]) => <option key={value} value={value}>{caption}</option>)}
      </select>
      {chooseFinding && <div>
        <label htmlFor={id + "-finding"}>Замечание</label>{" "}
        <select id={id + "-finding"} value={target} onChange={event => setSelectedFinding(event.target.value)} required>
          <option value="">Выберите замечание</option>
          {findingIds.map(id => <option value={id} key={id}>{escapeText(id)}</option>)}
        </select>
        {target && <dl><KeyValue label={targetLabel} value={target} /></dl>}
      </div>}
      {needsTarget && !chooseFinding && (boundTarget ? <dl><KeyValue label={targetLabel} value={boundTarget} /></dl> : <div>
        <label htmlFor={id + "-target"}>{targetLabel}</label>{" "}
        <input id={id + "-target"} value={targetInput} onChange={event => setTargetInput(event.target.value)} required />
      </div>)}
      <div>
        <label htmlFor={id + "-reason"}>Причина</label>{" "}
        <textarea id={id + "-reason"} value={reason} onChange={event => setReason(event.target.value)} maxLength={2000} required />
      </div>
      <Button type="submit" disabled={!valid}>Принять отклонение</Button>
    </fieldset>
    {mutation.error && <ErrorPanel error={mutation.error}
      {...(mutation.awaitsResult ? { onRetry: mutation.retry } : {})} />}
    {!mutation.awaitsResult && mutation.error instanceof ApiError && mutation.error.category === "validation" &&
      <Button onClick={mutation.reset}>Исправить отклонение</Button>}
  </form>;
}

export function DeviationCard({ item, embedded = false }: { item: DecisionRequest; embedded?: boolean }) {
  const payload = record(item.payload);
  const label = payload.finding_label ?? payload.summary;
  const content = <>
    {typeof label === "string" && <p>{escapeText(label)}</p>}
    <DeviationForm item={item} />
  </>;
  return embedded ? content : <InboxRequestCard item={item} title="Отклонение">{content}</InboxRequestCard>;
}
