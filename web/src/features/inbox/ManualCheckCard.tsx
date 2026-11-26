import { useId, useState } from "react";
import type { Uuid } from "../../api/generated/kernel";
import { field, record, useRecordManualVerdict, type DecisionRequest } from "../../api/hooks/execution";
import { KeyValue } from "../../components/data/KeyValue";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { escapeText } from "../../lib/safeText";
import { InboxRequestCard, useRequestAction } from "./QuestionCard";

export function ManualCheckCard({ item }: { item: DecisionRequest }) {
  const payload = record(item.payload);
  const checkId = payload.check_execution_id;
  const can = useRequestAction(item, "check.verdict", payload.actor_role);
  const mutation = useRecordManualVerdict(field(item.run_id, ""), field(checkId, ""));
  const [comment, setComment] = useState("");
  const id = useId();
  const showActions = can() && typeof checkId === "string" && checkId !== "" && mutation.status !== "success";

  function verdict(value: "pass" | "fail") {
    if (showActions && mutation.status === "idle") {
      mutation.recordVerdict({ check_execution_id: checkId as Uuid, verdict: value, comment: comment.trim() });
    }
  }

  return <InboxRequestCard item={item} title={field(payload.check_key ?? payload.summary, "Ручная проверка")}>
    {typeof payload.instructions === "string" && <p>{escapeText(payload.instructions)}</p>}
    {typeof checkId === "string" && <dl><KeyValue label="Проверка" value={checkId} /></dl>}
    {showActions && <>
      <fieldset disabled={mutation.status !== "idle"}>
        <legend>Вердикт</legend>
        <label htmlFor={id}>Комментарий</label>{" "}
        <textarea id={id} value={comment} onChange={event => setComment(event.target.value)} />
        <div className="confirm-actions">
          <Button onClick={() => verdict("fail")}>Не пройдена</Button>
          <Button onClick={() => verdict("pass")}>Пройдена</Button>
        </div>
      </fieldset>
      {mutation.error && <ErrorPanel error={mutation.error}
        {...(mutation.awaitsResult ? { onRetry: mutation.retry } : {})} />}
    </>}
  </InboxRequestCard>;
}
