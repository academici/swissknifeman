import type { KeySpecDoc } from "../../api/generated/config";
import type { EntryView, ExplainReportDefsKeyReport, GetSchemaView, ImportConfig } from "../../api/generated/settings";
import type { Document } from "../../api/generated/settings-document";
import { scopeName, type EntriesSnapshot, type SettingsScope } from "../../api/hooks/settings";
import { toNode, type SchemaRegistry } from "./profile";
import { isRecord, isSecretReference, jsonEqual, own } from "./values";

type SchemaKey = GetSchemaView["sections"][number]["keys"][number];
export type KeySpec = SchemaKey & Pick<KeySpecDoc, "write_permission">;
export type KeyReport = ExplainReportDefsKeyReport;
export type BaseRow = Pick<EntryView, "entry_id" | "op" | "value" | "locked" | "row_version">;
export type DraftOp = { op: "set" | "append"; value: unknown } | { op: "unset" | "remove" };
export type Draft = {
  readonly scope: SettingsScope;
  readonly level: SettingsScope["level"];
  readonly base: Readonly<Record<string, BaseRow | null>>;
  readonly entriesDigest: string;
  readonly ops: ReadonlyMap<string, DraftOp>;
};

export function schemaKey(key: SchemaKey, schema: unknown): KeySpec {
  const direct = own(key, "write_permission") ?? own(own(key.value_schema, "x-skm"), "write_permission");
  let property = own(own(schema, "properties"), key.key);
  if (property === undefined) {
    property = schema;
    for (const part of key.key.split(".").slice(1)) property = own(own(property, "properties"), part);
  }
  const permission = direct ?? own(own(property, "x-skm"), "write_permission");
  return typeof permission === "string" ? { ...key, write_permission: permission } : key;
}

export function fieldSchema(spec: KeySpec): Readonly<Record<string, unknown>> {
  if (spec.sensitivity === "secret") return { $ref: "urn:skm:config:secret-ref:v1" };
  const metadata = own(spec.value_schema, "x-skm");
  // The work-policy warning matrix has typed role/intensity entries.
  const typedWorkPolicyMap = spec.key.startsWith("execution.work_policy.") && spec.ui.widget === "json" &&
    isRecord(spec.value_schema.additionalProperties);
  const ui = typedWorkPolicyMap ? { ...spec.ui, widget: "map" } : spec.ui;
  return { ...spec.value_schema, "x-skm": { ...(isRecord(metadata) ? metadata : {}), ui } };
}

export function safeSettingValue(spec: KeySpec | undefined, registry: SchemaRegistry, value: unknown): unknown {
  if (value === undefined || value === null) return value;
  if (!spec) return "•••";
  const schema = fieldSchema(spec);
  if (spec.sensitivity === "secret" || toNode(schema, registry).kind === "secretRef") {
    return isSecretReference(value) ? value : "•••";
  }
  // The schema-form's fallback redactor also handles secrets inside objects and unsupported schemas.
  const redactor = toNode({ ...schema, not: {} }, registry);
  return redactor.kind === "unsupported" ? redactor.redact(value) : "•••";
}

export function fartherLock(scope: SettingsScope, report: KeyReport | undefined) {
  const lock = report?.locked_by;
  if (lock && (lock.level !== scope.level || (scope.level !== "instance" && lock.scope_id !== scope.scope_id))) {
    return lock;
  }
}

export function canWriteScope(level: SettingsScope["level"], rights: ReadonlySet<string>) {
  const shared = level === "instance" || level === "workspace" || level === "host";
  return rights.has("config.write") && (!shared || rights.has("config.write_shared"));
}

export function canWrite(scope: SettingsScope, rights: ReadonlySet<string>, spec: KeySpec, report?: KeyReport) {
  return spec.levels.includes(scope.level) && canWriteScope(scope.level, rights) &&
    (!spec.write_permission || rights.has(spec.write_permission)) && !fartherLock(scope, report);
}

export function startDraft(scope: SettingsScope, snapshot: EntriesSnapshot, knownKeys: Iterable<string>): Draft {
  return {
    scope, level: scope.level, entriesDigest: snapshot.digest, ops: new Map(),
    base: Object.fromEntries([
      ...Array.from(knownKeys, (key) => [key, null] as const),
      ...snapshot.entries.map((row) => [row.key, row] as const),
    ]),
  };
}

export function setDraftOp(draft: Draft, key: string, operation?: DraftOp): Draft {
  const base = draft.base[key] ?? null;
  const ops = new Map(draft.ops);
  if (!operation || (operation.op === "remove" && !base) || (base && operation.op === base.op &&
    (!("value" in operation) || jsonEqual(base.value, operation.value)))) {
    ops.delete(key);
  } else {
    ops.set(key, operation);
  }
  return { ...draft, ops };
}

export function sameRowVersion(base: BaseRow | null, current: BaseRow | null) {
  return base?.row_version === current?.row_version && base?.entry_id === current?.entry_id;
}

export function draftIsStale(draft: Draft, snapshot: EntriesSnapshot) {
  if (draft.entriesDigest !== snapshot.digest) return true;
  const current = new Map(snapshot.entries.map((row) => [row.key, row]));
  return [...draft.ops.keys()].some((key) => !sameRowVersion(draft.base[key] ?? null, current.get(key) ?? null));
}

export type RowState = Pick<BaseRow, "op" | "value" | "locked"> & Partial<Pick<BaseRow, "row_version">>;

export function desiredRow(base: BaseRow | null, operation: DraftOp): RowState | null {
  if (operation.op === "remove") return null;
  if (operation.op === "unset") return { op: "unset", locked: base?.locked ?? false };
  if ("value" in operation) return { op: operation.op, value: operation.value, locked: base?.locked ?? false };
  return null;
}

export interface ConflictRow {
  key: string;
  base: BaseRow | null;
  current: BaseRow | null;
  yours: RowState | null;
  status: "same" | "theirs" | "conflict";
}

export function sameRowState(left: RowState | null, right: RowState | null) {
  return left === right || (left !== null && right !== null && left.op === right.op && left.locked === right.locked &&
    (left.op === "unset" || jsonEqual(left.value, right.value)));
}

export function compareRow(key: string, base: BaseRow | null, current: BaseRow | null, yours: RowState | null): ConflictRow {
  const status = sameRowVersion(base, current) || sameRowState(current, yours) ? "same" : "conflict";
  return { key, base, current, yours, status };
}

export function compareDraft(draft: Draft, current: Draft): ConflictRow[] {
  return [...new Set([...Object.keys(draft.base), ...Object.keys(current.base), ...draft.ops.keys()])].flatMap((key) => {
    const before = draft.base[key] ?? null;
    const now = current.base[key] ?? null;
    const operation = draft.ops.get(key);
    if (operation) return [compareRow(key, before, now, desiredRow(before, operation))];
    return sameRowVersion(before, now) ? [] : [{ key, base: before, current: now, yours: before, status: "theirs" }];
  });
}

export function rebase(draft: Draft, current: Draft, takeCurrent: ReadonlySet<string>): Draft {
  let next = current;
  for (const [key, operation] of draft.ops) {
    if (!takeCurrent.has(key)) next = setDraftOp(next, key, operation);
  }
  return next;
}

function insertValue(doc: Record<string, unknown>, key: string, value: unknown) {
  const parts = key.split(".");
  const leaf = parts.pop();
  if (!leaf) throw new Error("Invalid settings key");
  let group = doc;
  for (const part of parts) {
    const existing = own(group, part);
    const next: Record<string, unknown> = isRecord(existing) ? existing : Object.create(null);
    group[part] = next;
    group = next;
  }
  group[leaf] = value;
}

export function draftImport(draft: Draft): ImportConfig {
  const replace = [...draft.ops.values()].some(({ op }) => op === "remove");
  const keys = replace ? new Set([...Object.keys(draft.base), ...draft.ops.keys()]) : draft.ops.keys();
  const rows = new Map(Array.from(keys, (key) => {
    const base = draft.base[key] ?? null;
    const operation = draft.ops.get(key);
    return [key, operation ? desiredRow(base, operation) : base] as const;
  }));
  return {
    scope: draft.scope, expected_entries_digest: draft.entriesDigest,
    document: settingsDocument(rows), format: "json", mode: replace ? "replace" : "merge",
  };
}

export function settingsDocument(rows: ReadonlyMap<string, RowState | null>) {
  const document: Record<string, unknown> & Pick<Document, "schema"> = Object.assign(Object.create(null), {
    schema: "urn:skm:settings:document:v1" as const,
  });
  const unset: string[] = [];
  const lock: string[] = [];
  const append: Record<string, unknown> = Object.create(null);

  for (const [key, row] of rows) {
    if (!row) continue;
    if (row.locked) lock.push(key);
    switch (row.op) {
      case "unset": unset.push(key); break;
      case "append": append[key] = row.value; break;
      case "set": insertValue(document, key, row.value); break;
    }
  }
  if (unset.length) document.unset = unset;
  if (lock.length) document.lock = lock;
  if (Object.keys(append).length) document.append = append;
  return document;
}

export function scopeHref(scope: SettingsScope) {
  return `/settings?${new URLSearchParams({ scope: scopeName(scope) })}`;
}
