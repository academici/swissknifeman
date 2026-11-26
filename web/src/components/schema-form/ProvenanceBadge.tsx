import type { ExplainReportDefsLayerRef } from "../../api/generated/settings";
import { escapeText } from "../../lib/safeText";
import { Badge } from "../primitives/Badge";
import { safeSettingValue, type KeyReport, type KeySpec } from "./draft";
import type { SchemaRegistry } from "./profile";

export function layerLabel(layer: ExplainReportDefsLayerRef) {
  const name = layer.label ?? layer.scope_id ?? layer.pack_id;
  return name ? `${layer.level} · ${name}` : layer.level;
}

export function SettingValue({ value }: { value: unknown }) {
  return value === undefined ? <>—</> : <code>{escapeText(JSON.stringify(value) ?? "—")}</code>;
}

export function ProvenanceBadge({ report, spec, registry }: { report: KeyReport; spec: KeySpec; registry: SchemaRegistry }) {
  const winner = report.winner;
  return (
    <details>
      <summary>
        Источник{" "}
        <Badge>{winner ? escapeText(layerLabel(winner)) : "—"}
          {winner?.row_version !== undefined && ` (v${winner.row_version})`}
        </Badge>
      </summary>
      <ul aria-label="Вклады уровней">
        {report.contributions.map((item, index) => (
          <li key={index}>
            {escapeText(layerLabel(item.layer))} · {escapeText(item.op)} · {escapeText(item.status)}
            {item.locked && " · 🔒"}
            {item.reason && ` · ${escapeText(item.reason)}`}
            {" "}<SettingValue value={safeSettingValue(spec, registry, item.value)} />
          </li>
        ))}
      </ul>
      {!!report.diagnostics?.length && (
        <ul aria-label="Диагностика">
          {report.diagnostics.map((item, index) => (
            <li key={index}>{escapeText(item.severity)} · {escapeText(item.code)} · {escapeText(item.message)}</li>
          ))}
        </ul>
      )}
    </details>
  );
}
