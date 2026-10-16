import { emptyDraft, setValue, unsetValue, valueOf } from "../draft";
import type { FormContext } from "../formContext";
import type { LeafSpec } from "../profile";
import type { Entry, Value } from "../types";
import { BooleanField } from "./BooleanField";
import { EnumField } from "./EnumField";
import type { FieldProps } from "./FieldFrame";
import { NumberField } from "./NumberField";
import { ReadOnlyField } from "./ReadOnlyField";
import { ScalarListField } from "./ScalarListField";
import { SecretRefField } from "./SecretRefField";
import { StringField } from "./StringField";

/** The entry of the view for a leaf; a leaf the view does not list (a new map entry) gets an empty one. */
export function entryOf(ctx: FormContext, spec: LeafSpec): Entry {
  const found = ctx.view.entries.find((entry) => entry.key === spec.key);
  if (found) return found;
  return {
    key: spec.key, type: spec.type === "unknown" ? "string" : spec.type, secret: spec.secret, description: spec.description,
    allowed_layers: spec.layers as Entry["allowed_layers"],
    effective: { value: null, layer: null, file: null, line: null, source: null }, overridden: [],
    layer_values: { machine: null, project: null },
  };
}

/** One leaf of the schema as the field of its type; disabled when the layer may not hold the key. */
export function LeafField({ spec, ctx }: { spec: LeafSpec; ctx: FormContext }) {
  const entry = entryOf(ctx, spec);
  const record = ctx.view.layers.find((layer) => layer.name === ctx.layer);
  const allowed = entry.allowed_layers;
  let reason: string | null = null;
  if (!record?.writable) reason = `the ${ctx.layer} layer is not writable here`;
  else if (allowed && !allowed.includes(ctx.layer)) reason = `allowed: ${allowed.join(", ")}`;
  const disabled = reason !== null;
  const draft = ctx.draft ?? emptyDraft(ctx.view, ctx.layer);
  const value: Value | null = draft ? valueOf(draft, entry.key) : ((entry.layer_values[ctx.layer] as Value | null) ?? null);
  const props: FieldProps = {
    spec, entry, value, disabled, reason, changed: ctx.draft?.ops.has(entry.key) ?? false,
    onSet: (next) => draft && ctx.onDraft(setValue(draft, entry.key, next)),
    onUnset: () => draft && ctx.onDraft(unsetValue(draft, entry.key)),
  };
  if (spec.unsupported.length > 0 || spec.type === "unknown") return <ReadOnlyField {...props} />;
  if (spec.secret) return <SecretRefField {...props} />;
  if (spec.enum && spec.type !== "array") return <EnumField {...props} />;
  switch (spec.type) {
    case "boolean":
      return <BooleanField {...props} />;
    case "integer":
    case "number":
      return <NumberField {...props} />;
    case "array":
      return <ScalarListField {...props} />;
    default:
      return <StringField {...props} />;
  }
}
