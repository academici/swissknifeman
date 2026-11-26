import type { PluginDoc } from "./api";

/** The words of the enforcement statuses; the value comes from the API as it is and its text is always shown. */
export const ENFORCEMENT_LABELS: Record<string, string> = {
  declared: "declared",
  advisory: "advisory",
  enforced: "enforced",
};

const STATE_TONE: Record<string, string> = {
  healthy: "ok",
  enabled: "ok",
  starting: "warn",
  degraded: "warn",
  compatible: "unknown",
  discovered: "unknown",
  disabled: "unknown",
  permission_denied: "warn",
  quarantined: "fail",
  incompatible: "fail",
  invalid: "fail",
};

/** The state as text (colour is only an addition). */
export function StateBadge({ state }: { state: PluginDoc["state"] }) {
  return <span className={`status status-${STATE_TONE[state] ?? "unknown"}`}>{state.replace(/_/g, " ")}</span>;
}

export function EnforcementBadge({ value }: { value: string }) {
  return <span className={`status enforcement enforcement-${value.replace(/[^a-z]/g, "")}`}>{ENFORCEMENT_LABELS[value] ?? value}</span>;
}

export function Flag({ label, on }: { label: string; on: boolean }) {
  return (
    <span className={`flag ${on ? "flag-on" : "flag-off"}`}>
      {label} {on ? "on" : "off"}
    </span>
  );
}
