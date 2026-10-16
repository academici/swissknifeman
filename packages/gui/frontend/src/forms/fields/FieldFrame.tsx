import type { ReactNode } from "react";
import type { LeafSpec } from "../profile";
import { hintOf } from "../profile";
import { ProvenanceBadge } from "../ProvenanceBadge";
import type { Entry, Value } from "../types";

export interface FieldProps {
  spec: LeafSpec;
  entry: Entry;
  /** What the layer holds for the key with the draft applied (`null`: not set). */
  value: Value | null;
  disabled: boolean;
  /** Why the field is disabled, shown as a hint. */
  reason: string | null;
  changed: boolean;
  onSet: (value: Value) => void;
  onUnset: () => void;
}

export const fieldId = (key: string) => `field-${key}`;

/** The frame of every field: label (the dotted key), hints, provenance and the unset button. */
export function FieldFrame({ props, children, error }: { props: FieldProps; children: ReactNode; error?: string | null }) {
  const { spec, entry, disabled, reason, changed, value } = props;
  const hint = hintOf(spec);
  return (
    <div className={`cfg-field${changed ? " changed" : ""}${disabled ? " disabled" : ""}`} data-key={entry.key}>
      <label htmlFor={fieldId(entry.key)}>{entry.key}</label>
      <div className="cfg-control">{children}</div>
      {!disabled && value !== null && (
        <button type="button" className="link-button" aria-label={`Unset ${entry.key}`} onClick={props.onUnset}>
          Unset
        </button>
      )}
      {error ? <div className="cfg-error" role="alert">{error}</div> : null}
      {reason ? <div className="muted cfg-reason">{reason}</div> : null}
      {hint ? <div className="muted cfg-hint">{hint}</div> : null}
      {entry.description ? <div className="muted cfg-description">{entry.description}</div> : null}
      <ProvenanceBadge entry={entry} />
    </div>
  );
}
