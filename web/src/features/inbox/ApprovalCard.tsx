import { useId, useState } from "react";
import type { IntentApprovalView } from "../../api/generated/policy";
import { record, useInboxPermissions, type DecisionRequest } from "../../api/hooks/execution";
import { useInboxIntent, useResolveIntent } from "../../api/hooks/policy";
import { DataList } from "../../components/data/DataList";
import { KeyValue } from "../../components/data/KeyValue";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { Spinner } from "../../components/primitives/Spinner";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";
import { RequestMetadata } from "./QuestionCard";

type InboxIntent = Omit<IntentApprovalView, "effect_id"> & { effect_id: string | undefined };

function IntentDetails({ intent }: { intent: InboxIntent }) {
  const approval = intent.approvals.find(approval => approval.decision === "approve" && approval.args_digest === intent.args_digest);
  const json = JSON.stringify(intent.normalized_args, null, 2);
  return (
    <DataList>
      <KeyValue label="Состояние" value={<StatusBadge status={intent.state} />} />
      <KeyValue label="kind" value={intent.kind} />
      <KeyValue label="effect_id" value={intent.effect_id ?? "Не указан"} />
      <KeyValue label="subject_ref" value={intent.subject_ref} />
      <KeyValue label="risk" value={intent.risk} />
      <KeyValue label="expires_at" value={intent.expires_at} />
      <KeyValue label="single_use" value={String(intent.single_use ?? approval?.single_use ?? "Не указано")} />
      <KeyValue label="args_digest" value={intent.args_digest} />
      <KeyValue label="normalized_args" value={
        <div className="code-block">
          <pre tabIndex={0}><code>{json.split("\n").map(escapeText).join("\n")}</code></pre>
        </div>
      } />
    </DataList>
  );
}

type Review = { action: "approve" | "deny"; intent: InboxIntent };

export function ApprovalCard({ intentId, request }: { intentId: string; request: DecisionRequest | undefined }) {
  const query = useInboxIntent(intentId);
  const mutation = useResolveIntent(intentId);
  const heading = useId();
  const [review, setReview] = useState<Review | null>(null);
  const [confirming, setConfirming] = useState(false);
  const payload = record(request?.payload);
  const linkedEffect = record(payload.refs).effect_id ?? payload.effect_id;
  const fresh = query.data?.intent_id === intentId ? query.data : undefined;
  // Confirmation and retry use the snapshot the operator opened, even when replay refreshes the query.
  const intent = review?.intent ?? (fresh && {
    ...fresh,
    effect_id: typeof linkedEffect === "string" && linkedEffect !== "" ? linkedEffect : fresh.effect_id,
  });
  const open = fresh?.state === "proposed" && (!request || request.state === "open");
  const allowed = useInboxPermissions(open ? fresh.scope_id : null);
  const canResolve = open && intent?.scope_id === fresh.scope_id &&
    typeof intent.effect_id === "string" && intent.effect_id !== "" &&
    typeof intent.single_use === "boolean" && allowed("intent.approve");
  const error = mutation.error;

  function start(action: Review["action"]) {
    if (!canResolve || !intent || review || mutation.status !== "idle") return;
    setReview({ action, intent });
    setConfirming(true);
  }

  function submit(reason: string) {
    if (!review || !canResolve || mutation.status !== "idle") return;
    const { intent_id, row_version, args_digest, single_use } = review.intent;
    if (typeof single_use !== "boolean") return;
    const command = { intent_id, expected_row_version: row_version };
    const runId = typeof request?.run_id === "string" ? request.run_id : undefined;
    if (review.action === "approve") mutation.resolve({ ...command, args_digest, single_use }, runId);
    else mutation.resolve({ ...command, reason }, runId);
    setConfirming(false);
  }

  async function reload() {
    const next = await query.refetch();
    if (!next.isSuccess || next.data?.intent_id !== intentId) return;
    if (mutation.awaitsResult && next.data.state === "proposed") return;
    mutation.reconcile();
    setReview(null);
  }

  return (
    <article aria-labelledby={heading}>
      <h3 id={heading}>Одобрение{intent ? ` · ${escapeText(intent.kind)}` : ""}</h3>
      {request && <RequestMetadata item={request} />}
      {intent && <IntentDetails intent={intent} />}
      {intent?.reason && <p>{escapeText(intent.reason)}</p>}
      {query.isPending && <Spinner />}
      {query.isError && <ErrorPanel error={query.error} onRetry={() => { void query.refetch(); }} />}
      {canResolve && !query.isError && !review && mutation.status === "idle" && <div className="confirm-actions">
        <Button onClick={() => start("deny")}>Отклонить</Button>
        <Button onClick={() => start("approve")}>Одобрить</Button>
      </div>}
      {mutation.isPending && <Spinner label="Отправка решения…" />}
      {mutation.status === "success" && <p role="status">Решение записано.</p>}
      {error && <>
        <ErrorPanel error={error}
          {...(mutation.awaitsResult && canResolve ? { onRetry: mutation.retry } : {})} />
        <Button disabled={query.isFetching} onClick={() => { void reload(); }}>Загрузить текущую версию</Button>
      </>}
      {review && confirming && <ConfirmDialog open title={review.action === "approve" ? "Одобрить эффект" : "Отклонить эффект"}
        confirmLabel={review.action === "approve" ? "Подтвердить одобрение" : "Подтвердить отказ"}
        requireReason={review.action === "deny"} onClose={() => { setConfirming(false); setReview(null); }}
        onConfirm={submit}>
        <IntentDetails intent={review.intent} />
        {!canResolve && <p role="status">Решение по этому эффекту сейчас недоступно.</p>}
      </ConfirmDialog>}
    </article>
  );
}
