import { useState } from "react";
import type { ReviewReceipt } from "../../api/generated/execution_10";
import { field, useFixBrief, useRunRead, type ReadRecord } from "../../api/hooks/execution";
import { EmptyState } from "../../components/data/EmptyState";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";
import { EvidenceRefs } from "./ChecksPanel";
import { FileDownload } from "./StepPanel";

function FixBrief({ id }: { id: string }) {
  const brief = useFixBrief(id);
  if (brief.isError) return <ErrorPanel error={brief.error} onRetry={() => { void brief.refetch(); }} />;
  if (!brief.data) return <Skeleton />;
  return <>
    <JsonView value={brief.data.document} />
    {brief.data.full_report_file_version_id && <FileDownload
      versionId={brief.data.full_report_file_version_id} label="Скачать полный отчёт"
    />}
  </>;
}

function Findings({ findings }: { findings: readonly ReadRecord[] }) {
  return <>
    <h3>Замечания</h3>
    {findings.length ? <ul>{findings.map((finding, index) =>
      <li key={field(finding.finding_id, String(index))}>
        <StatusBadge status={field(finding.severity)} /> <StatusBadge status={field(finding.state)} />
        <dl>
          <KeyValue label="Ключ замечания" value={field(finding.finding_key)} />
          {finding.first_seen_review_id != null && finding.first_seen_review_id !== finding.review_id &&
            <KeyValue label="Впервые зафиксировано в ревью" value={field(finding.first_seen_review_id)} />}
          {finding.review_id != null && <KeyValue label="Ревью" value={field(finding.review_id)} />}
          {finding.output_id != null && <KeyValue label="Результат" value={field(finding.output_id)} />}
        </dl>
        <p>{escapeText(field(finding.message ?? finding.summary))}</p>
      </li>
    )}</ul> : <EmptyState title="Нет замечаний" />}
  </>;
}

export function ReviewPanel({ reviews, findings, fixBriefIds = [] }: {
  reviews: readonly ReadRecord[];
  findings: readonly ReadRecord[];
  fixBriefIds?: readonly string[];
}) {
  const briefs = new Set(fixBriefIds);
  for (const entry of [...reviews, ...findings]) {
    if (typeof entry.fix_brief_id === "string") briefs.add(entry.fix_brief_id);
  }
  return <section>
    <h2>Ревью</h2>
    {reviews.length ? <ul>{reviews.map((review, index) =>
      <li key={field(review.review_id, String(index))}>
        Раунд {escapeText(field(review.round_no))} · {escapeText(field(review.profile_key))}{" "}
        <StatusBadge status={field(review.verdict ?? review.state)} />
        <dl>
          <KeyValue label="Ревью" value={field(review.review_id)} />
          {review.output_id != null && <KeyValue label="Результат" value={field(review.output_id)} />}
          <KeyValue label="Остаточный риск" value={field(review.residual_risk)} />
        </dl>
        <EvidenceRefs value={review.evidence_refs} />
        <Findings findings={findings.filter(finding => finding.review_id === review.review_id)} />
      </li>
    )}</ul> : <EmptyState title="Нет раундов ревью" />}
    {[...briefs].map(id => <FixBriefDetails key={id} id={id} />)}
  </section>;
}

export function FixBriefDetails({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Задание на исправление · {escapeText(id)}</summary>
    {open && <FixBrief id={id} />}
  </details>;
}

export function ReviewReceiptPanel({ runId }: { runId: string }) {
  const receipt = useRunRead<ReviewReceipt>(runId, "/review-receipt");
  return <section>
    <h2>Квитанция ревью</h2>
    {receipt.isError ? <ErrorPanel error={receipt.error} onRetry={() => { void receipt.refetch(); }} />
      : receipt.data ? <>
        <StatusBadge status={receipt.data.status} />{" "}
        {receipt.data.verdict && <StatusBadge status={receipt.data.verdict} />}
        <dl>
          <KeyValue label="Запрос ревью" value={receipt.data.request_id} />
          <KeyValue label="Результат" value={receipt.data.output_id} />
          <KeyValue label="Дайджест дерева" value={receipt.data.tree_digest} />
          <KeyValue label="Базовый коммит" value={receipt.data.base_commit} />
          <KeyValue label="Итоговый коммит" value={receipt.data.head_commit} />
        </dl>
        <Findings findings={receipt.data.findings} />
      </> : <Skeleton />}
  </section>;
}
