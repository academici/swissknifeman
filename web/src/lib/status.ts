export type Tone = "neutral" | "success" | "info" | "warning" | "danger";

const tones = new Map<string, Tone>();

const groups: Record<Tone, readonly string[]> = {
  neutral: ["created", "pending", "queued", "skipped", "cancelled", "superseded", "waived", "archived", "nit", "unknown"],
  success: ["green", "passed", "succeeded", "completed", "accepted", "resolved", "ready"],
  info: ["running", "assigned", "executing", "checking", "reviewing", "integrating", "active", "open"],
  warning: ["waiting", "manual_pending", "paused", "blocked", "attention", "minor", "rework_required", "awaiting_decision", "deferred"],
  danger: ["red", "failed", "timed_out", "rejected", "error", "blocker", "major", "confirmed", "killed"],
};

for (const [tone, statuses] of Object.entries(groups) as [Tone, readonly string[]][]) {
  for (const status of statuses) tones.set(status, tone);
}

export function statusTone(status: string): Tone {
  return tones.get(status) ?? "neutral";
}
