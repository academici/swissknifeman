import type { ReactNode } from "react";
import { field, record, type DecisionRequest } from "../../api/hooks/execution";
import { escapeText } from "../../lib/safeText";
import { AnswerForm, InboxRequestCard } from "./QuestionCard";

export function EscalationCard({ item, deviation }: { item: DecisionRequest; deviation?: ReactNode }) {
  const payload = record(item.payload);
  const code = payload.code ?? record(record(item.blocking_reason).refs).stop_code;
  return <InboxRequestCard item={item} title={field(code ?? item.summary, "Эскалация")}>
    {typeof payload.summary === "string" && <p>{escapeText(payload.summary)}</p>}
    <AnswerForm item={item} escalation />
    {deviation}
  </InboxRequestCard>;
}
