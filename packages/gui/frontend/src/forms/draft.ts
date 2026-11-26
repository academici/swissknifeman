// The draft of a change: the operations the user made in order, the layer and revision they were made on and the
// layer values of that revision (the base of the three-way view). Parsing of input is by type only; the schema's
// limits are decided by the backend preview (D6).
import type { ConfigView, LayerName, PreviewRequest, Value } from "./types";
import { MUTATION_CONTRACT } from "./types";

export type DraftOp = { op: "set"; value: Value } | { op: "unset" };

export interface Draft {
  module: string;
  layer: LayerName;
  /** Revision of the layer in the view the draft started on. */
  revision: string;
  /** The value of every key in the layer at that revision; absent: not set. */
  base: Record<string, Value | null>;
  /** Operations by key, in the order of editing. */
  ops: Map<string, DraftOp>;
}

export function layerValues(view: ConfigView, layer: LayerName): Record<string, Value | null> {
  const values: Record<string, Value | null> = {};
  for (const entry of view.entries) values[entry.key] = (entry.layer_values[layer] as Value | null) ?? null;
  return values;
}

/** The writable layer record of a view, or `undefined`. */
export function layerOf(view: ConfigView, layer: LayerName) {
  return view.layers.find((candidate) => candidate.name === layer);
}

export function emptyDraft(view: ConfigView, layer: LayerName): Draft | null {
  const record = layerOf(view, layer);
  if (!record || !record.writable || record.revision === null) return null;
  return { module: view.module, layer, revision: record.revision, base: layerValues(view, layer), ops: new Map() };
}

export function sameValue(left: Value | null | undefined, right: Value | null | undefined): boolean {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

function withOp(draft: Draft, key: string, op: DraftOp | null): Draft {
  const ops = new Map(draft.ops);
  ops.delete(key);
  if (op) ops.set(key, op);
  return { ...draft, ops };
}

/** Set a key; a value equal to the one in the file takes the operation back. */
export function setValue(draft: Draft, key: string, value: Value): Draft {
  const base = draft.base[key] ?? null;
  return withOp(draft, key, base !== null && sameValue(base, value) ? null : { op: "set", value });
}

/** Remove a key from the layer; a key that is not in the file needs no operation. */
export function unsetValue(draft: Draft, key: string): Draft {
  return withOp(draft, key, (draft.base[key] ?? null) === null ? null : { op: "unset" });
}

export function clearOp(draft: Draft, key: string): Draft {
  return withOp(draft, key, null);
}

/** What the layer would hold for a key with the draft applied. */
export function valueOf(draft: Draft, key: string): Value | null {
  const op = draft.ops.get(key);
  if (op) return op.op === "set" ? op.value : null;
  return draft.base[key] ?? null;
}

export function toPatch(draft: Draft): PreviewRequest["patch"] {
  return [...draft.ops].map(([key, op]) => (op.op === "set" ? { op: "set" as const, key, value: op.value } : { op: "unset" as const, key }));
}

export function previewRequest(draft: Draft): PreviewRequest {
  return { $schema: MUTATION_CONTRACT, kind: "preview_request", module: draft.module, layer: draft.layer,
    expected_revision: draft.revision, patch: toPatch(draft) } as PreviewRequest;
}

/** The text of an integer; `null` when it is not one. */
export function parseInteger(text: string): number | null {
  return /^[+-]?\d+$/.test(text.trim()) && Number.isSafeInteger(Number(text)) ? Number(text) : null;
}

/** The text of a number; `null` when it is not a finite one. */
export function parseNumber(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export type Status = "same" | "theirs" | "conflict";

export interface KeyState {
  key: string;
  base: Value | null;
  current: Value | null;
  /** The draft's value; `undefined` when the key is not in the draft. */
  mine: Value | null | undefined;
  status: Status;
}

/**
 * Three-way comparison by key. `theirs`: only the file changed; `conflict`: the file and the draft changed the key
 * to different values; `same`: the draft's key still applies cleanly (the file has not changed it or made the same
 * change). Only keys that the draft or the file changed are listed.
 */
export function threeWay(draft: Draft, current: Record<string, Value | null>): KeyState[] {
  const keys = new Set<string>([...draft.ops.keys()]);
  for (const key of Object.keys({ ...draft.base, ...current })) {
    if (!sameValue(draft.base[key], current[key])) keys.add(key);
  }
  const states: KeyState[] = [];
  for (const key of keys) {
    const base = draft.base[key] ?? null;
    const now = current[key] ?? null;
    const op = draft.ops.get(key);
    const mine = op === undefined ? undefined : op.op === "set" ? op.value : null;
    let status: Status;
    if (mine === undefined) status = "theirs";
    else if (sameValue(base, now) || sameValue(mine, now)) status = "same";
    else status = "conflict";
    states.push({ key, base, current: now, mine, status });
  }
  return states;
}

/** The same operations on the layer as it is now. */
export function rebase(draft: Draft, view: ConfigView): Draft | null {
  const fresh = emptyDraft(view, draft.layer);
  if (!fresh) return null;
  const ops = new Map<string, DraftOp>();
  for (const [key, op] of draft.ops) {
    const now = fresh.base[key] ?? null;
    if (op.op === "set" ? sameValue(op.value, now) : now === null) continue; // nothing left to change
    ops.set(key, op);
  }
  return { ...fresh, ops };
}
