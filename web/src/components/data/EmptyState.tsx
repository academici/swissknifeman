import type { PropsWithChildren } from "react";
import { escapeText } from "../../lib/safeText";

export function EmptyState({ title, children }: PropsWithChildren<{ title: string }>) {
  return <section className="empty-state"><h2>{escapeText(title)}</h2>{children}</section>;
}
