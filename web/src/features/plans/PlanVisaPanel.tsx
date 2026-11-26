import { useState } from "react";
import { isUuid, useApprovePlanVisa, usePlanVisa, useVisaReadiness, useVisaReadinessReport } from "../../api/hooks/planning";
import { RelativeTime } from "../../components/data/RelativeTime";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";

const ready = (status: string | undefined) => status === "ready" || status === "ready_with_advisories";

export default function PlanVisaPanel({ planId, revisionId, canApprove, canValidate }: {
  planId: string; revisionId: string; canApprove: boolean; canValidate: boolean;
}) {
  const visa = usePlanVisa(planId, revisionId);
  const approval = useApprovePlanVisa(planId, revisionId);
  const validation = useVisaReadiness(planId, revisionId);
  const [report, setReport] = useState("");
  const [loaded, setLoaded] = useState("");
  const [reason, setReason] = useState("");
  const reportRead = useVisaReadinessReport(loaded);
  const signature = visa.data?.latest_signature;
  const generated = validation.data?.report_id === report ? validation.data : undefined;
  const loadedReport = reportRead.data?.report;
  const matchingReport = loaded === report && loadedReport?.plan_id === planId && loadedReport.revision_id === revisionId;
  const status = generated?.status ?? (matchingReport ? reportRead.data?.effective_status : undefined);
  return <section aria-label="PlanVisa">
    <h3>PlanVisa</h3>
    {visa.error ? <ErrorPanel error={visa.error} onRetry={() => void visa.refetch()} /> : visa.data ? signature ? <>
      <p>Последняя подпись <RelativeTime value={signature.signed_at} /></p>
      <dl><dt>ID визы</dt><dd><code>{escapeText(signature.visa_id)}</code></dd>
        <dt>Отчёт о готовности</dt><dd><code>{escapeText(signature.readiness_report_id)}</code></dd></dl>
    </> : <p>Подписей пока нет.</p> : <Skeleton />}
    {canValidate && <Button disabled={validation.isPending || approval.isPending}
      onClick={() => validation.mutate({ mode: "full" }, { onSuccess: result => {
        setReport(result.report_id); setLoaded(""); approval.reset();
      } })}>Проверить готовность ревизии</Button>}
    {validation.error && <ErrorPanel error={validation.error} />}
    {generated?.findings.length ? <ul>{generated.findings.map((finding, index) =>
      <li key={index}>{escapeText(String(finding.message ?? finding.code ?? ""))}</li>)}</ul> : null}
    {(canApprove || status) && <form onSubmit={event => {
      event.preventDefault();
      if (canApprove && isUuid(report) && ready(status) && !approval.isPending && reason.trim()) {
        approval.mutate({ readiness_report_id: report, reason: reason.trim() },
          { onSuccess: () => setReason("") });
      }
    }}>
      {canApprove && <>
        <label>ID отчёта о готовности <input value={report} disabled={validation.isPending || approval.isPending}
          onChange={event => { setReport(event.target.value.trim()); setLoaded(""); approval.reset(); }} /></label>
        <Button disabled={!isUuid(report) || reportRead.isFetching || approval.isPending || validation.isPending}
          onClick={() => { if (loaded === report) void reportRead.refetch(); else setLoaded(report); }}>Загрузить отчёт</Button>
        {reportRead.error && <ErrorPanel error={reportRead.error} />}
        {loadedReport && !matchingReport && <p role="alert">Отчёт относится к другой ревизии.</p>}
      </>}
      {status && <p>Готовность <StatusBadge status={status} /></p>}
      {canApprove && <>
        <label>Причина одобрения <textarea required maxLength={2000} value={reason}
          onChange={event => setReason(event.target.value)} disabled={approval.isPending} /></label>
        <Button type="submit" disabled={!ready(status) || !reason.trim() || validation.isPending || approval.isPending}>
          Подписать визу
        </Button>
        {approval.error && <ErrorPanel error={approval.error} />}
      </>}
    </form>}
  </section>;
}
