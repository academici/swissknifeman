import type { PropsWithChildren } from "react";
import type { Tone } from "../../lib/status";

export function Badge({ tone = "neutral", children }: PropsWithChildren<{ tone?: Tone }>) {
  return <span className="badge" data-tone={tone}>{children}</span>;
}
