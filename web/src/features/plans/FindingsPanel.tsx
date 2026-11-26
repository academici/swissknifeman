import type { ValidationReportView } from "../../api/generated/planning";
import { Button } from "../../components/primitives/Button";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { isRecord } from "../../components/schema-form/values";
import { escapeText } from "../../lib/safeText";

export type Finding = ValidationReportView["findings"][number];
type RuleFailure = ValidationReportView["rule_failures"][number];
export type Findings = Pick<ValidationReportView, "findings" | "rule_failures">;

export function problemFindings(details: Record<string, unknown>): Findings {
  const findings = Array.isArray(details.findings) ? details.findings.filter((row): row is Finding =>
    isRecord(row) && typeof row.code === "string" && typeof row.message === "string" &&
    ["error", "warning", "info"].includes(String(row.severity)) &&
    [row.entity_id, row.entity_key, row.pointer].every((field) => field === null || typeof field === "string"),
  ) : [];
  const rule_failures = Array.isArray(details.rule_failures) ? details.rule_failures.filter((row): row is RuleFailure =>
    isRecord(row) && typeof row.rule === "string" && typeof row.error_type === "string" && typeof row.message === "string",
  ) : [];
  return { findings, rule_failures };
}

export function FindingsPanel({ report, onSelect }: { report: Findings; onSelect?: (finding: Finding) => void }) {
  return <section aria-label="Findings">
    <h3>Findings ({report.findings.length})</h3>
    {!!report.findings.length && <ul>{report.findings.map((finding, index) => {
      const label = [finding.code, finding.entity_key, finding.message, finding.pointer].filter(Boolean).join(" · ");
      return <li key={index}>
        <StatusBadge status={finding.severity} />{" "}
        {onSelect && (finding.entity_id || finding.entity_key || finding.pointer)
          ? <Button onClick={() => onSelect(finding)}>{escapeText(label)}</Button> : escapeText(label)}
      </li>;
    })}</ul>}
    {!!report.rule_failures.length && <section>
      <h4>Ошибки правил проверки</h4>
      <ul>{report.rule_failures.map((failure, index) => <li key={index}>
        {escapeText([failure.rule, failure.plugin, failure.error_type, failure.message].filter(Boolean).join(" · "))}
      </li>)}</ul>
    </section>}
  </section>;
}
