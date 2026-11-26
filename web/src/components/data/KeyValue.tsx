import type { ReactNode } from "react";
import { escapeText } from "../../lib/safeText";
import { CopyId } from "./CopyId";

export function KeyValue({ label, value, id }: { label: string; value: ReactNode; id?: string }) {
  return (
    <div>
      <dt>{escapeText(label)}</dt>
      <dd>{typeof value === "string" ? escapeText(value) : value} {id !== undefined && <CopyId id={id} />}</dd>
    </div>
  );
}
