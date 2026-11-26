import { escapeText } from "../../lib/safeText";
import { statusTone } from "../../lib/status";
import { Badge } from "./Badge";

export function StatusBadge({ status }: { status: string | null | undefined }) {
  return <Badge tone={statusTone(status ?? "unknown")}>{escapeText(status ?? "Неизвестно")}</Badge>;
}
