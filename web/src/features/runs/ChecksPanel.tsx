import { field, record, type ReadRecord } from "../../api/hooks/execution";
import { SafeLink } from "../../components/content/SafeLink";
import { EmptyState } from "../../components/data/EmptyState";
import { KeyValue } from "../../components/data/KeyValue";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";
import { FileDownload } from "./StepPanel";

export function WaitingForHuman() {
  return <p role="status">Ожидает действий человека. <SafeLink href="/inbox">Перейти во входящие</SafeLink></p>;
}

export function EvidenceRefs({ value }: { value: unknown }) {
  if (!Array.isArray(value) || !value.length) return null;
  return <ul>{value.map(record).map(ref => typeof ref.file_version_id === "string" &&
    <li key={`${field(ref.role)}:${ref.file_version_id}`}>
      <code>{escapeText(ref.file_version_id)}</code>{" "}
      <FileDownload versionId={ref.file_version_id} label={`Скачать доказательство · ${field(ref.role)}`} />
    </li>)}</ul>;
}

export function ChecksPanel({ checks }: { checks: readonly ReadRecord[] }) {
  return <section>
    <h2>Проверки</h2>
    {checks.length === 0 ? <EmptyState title="Нет проверок" /> : <ul>{checks.map((check, index) => {
      const waiting = check.state === "manual_pending" || check.state === "WAITING_MANUAL_CHECK";
      return <li key={field(check.check_execution_id, String(index))}>
        {escapeText(field(check.check_key ?? check.check_spec_id ?? check.kind))}{" "}
        <StatusBadge status={waiting ? "manual_pending" : field(check.state)} />
        {waiting && <WaitingForHuman />}
        {typeof check.summary === "string" && <p>{escapeText(check.summary)}</p>}
        <dl>
          <KeyValue label="Выполнение проверки" value={field(check.check_execution_id)} />
          {check.output_id != null && <KeyValue label="Результат" value={field(check.output_id)} />}
          {check.round_no != null && <KeyValue label="Раунд проверки" value={field(check.round_no)} />}
          {check.exit_code != null && <KeyValue label="Код выхода" value={field(check.exit_code)} />}
        </dl>
        <EvidenceRefs value={check.evidence_refs} />
      </li>;
    })}</ul>}
  </section>;
}
