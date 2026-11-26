import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import executionDefs from "../../../../src/skm/schemas/execution/defs.v1.json";
import integrationDefs from "../../../../src/skm/schemas/integrations/defs.v1.json";
import kernelDefs from "../../../../src/skm/schemas/kernel/defs.v1.json";
import policyLayer from "../../../../src/skm/schemas/policy/permission-layer.v1.json";
import policyProfile from "../../../../src/skm/schemas/policy/profile.v1.json";
import { ApiError } from "../../api/errors";
import type { ExplainReport, GetSchemaView } from "../../api/generated/settings";
import {
  isSettingsConflict, parseSettingsScope, scopeName, SettingsReadContext, useRefreshSettings, useSettingsEntries,
  useSettingsExplain, useSettingsPermissions, useSettingsQueryScope, useSettingsSchema, useSettingsStream,
  writeSetting, type EntriesSnapshot, type RowWrite,
  type SettingsLevel, type SettingsScope,
} from "../../api/hooks/settings";
import { useIdempotentMutation } from "../../api/idempotency";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";
import { Spinner } from "../../components/primitives/Spinner";
import { ConflictView } from "../../components/schema-form/ConflictView";
import {
  canWrite, canWriteScope, compareDraft, compareRow, draftImport, draftIsStale, rebase, sameRowVersion, safeSettingValue,
  schemaKey, setDraftOp, startDraft, type BaseRow, type Draft, type DraftOp, type KeySpec,
} from "../../components/schema-form/draft";
import { LevelPicker } from "../../components/schema-form/LevelPicker";
import { PreviewDialog, type PreviewPolicy } from "../../components/schema-form/PreviewDialog";
import { schemaTouchesSecret } from "../../components/schema-form/profile";
import { own } from "../../components/schema-form/values";
import { escapeText } from "../../lib/safeText";
import { ExportButton } from "./ExportButton";
import { ImportDialog } from "./ImportDialog";
import { KeyRow } from "./KeyRow";
import { filterSections, SectionTree } from "./SectionTree";

const bundledSchemas = [executionDefs, integrationDefs, kernelDefs, policyLayer, policyProfile];

const instance: SettingsScope = { level: "instance" };

export default function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const { scope } = useScope();
  const fallback = (scope.projectId ? parseSettingsScope(`project:${scope.projectId}`) : undefined) ??
    (scope.workspaceId ? parseSettingsScope(`workspace:${scope.workspaceId}`) : undefined) ?? instance;
  const queryScope = params.get("scope");
  const viewed = queryScope === null ? fallback : parseSettingsScope(queryScope);

  if (!viewed) return <section className="section">
    <h1>Настройки</h1>
    <p role="alert">Не удалось распознать область настроек.</p>
    <Button onClick={() => setParams({ scope: scopeName(fallback) })}>Открыть текущую область</Button>
  </section>;

  return <SettingsBinding key={scopeName(viewed)} viewed={viewed} />;
}

function SettingsBinding({ viewed }: { viewed: SettingsScope }) {
  const resolved = useSettingsQueryScope(viewed);
  const read = useSettingsStream(resolved.data ?? { workspaceId: null, projectId: null });
  if (!resolved.data) return <section className="section">
    <h1>Настройки</h1>
    {resolved.isError ? <ErrorPanel error={resolved.error} onRetry={() => void resolved.refetch()} /> :
      <Spinner label="Загрузка настроек…" />}
  </section>;
  return <SettingsReadContext.Provider value={read}><SettingsScopeView viewed={viewed} /></SettingsReadContext.Provider>;
}

function SettingsScopeView({ viewed }: { viewed: SettingsScope }) {
  const [params, setParams] = useSearchParams();
  const report = useSettingsExplain(viewed);
  const known = new Map<SettingsLevel, SettingsScope>([["instance", instance]]);
  for (const layer of report.data?.chain ?? []) {
    const scope = parseSettingsScope(layer.level === "instance" ? "instance" : `${layer.level}:${layer.scope_id ?? ""}`);
    if (scope) known.set(scope.level, { ...scope, ...(layer.label && { label: layer.label }) });
  }
  known.set(viewed.level, report.data?.scope ?? viewed);
  const level = params.get("level");
  const target = [...known.values()].find((scope) => scope.level === level) ?? viewed;

  return <section className="section">
    <h1>Настройки</h1>
    <p>Область просмотра <code>{escapeText(scopeName(viewed))}</code>
      {report.data?.scope.label && <> · {escapeText(report.data.scope.label)}</>}
      {report.data && <> · Поколение {report.data.generation}</>}
    </p>
    {report.isError && <ErrorPanel error={report.error} onRetry={() => void report.refetch()} />}
    <SettingsTarget key={scopeName(target)} target={target} known={known} visibleReport={report.data}
      onSelect={(next, inChain) => {
        const updated = new URLSearchParams(params);
        updated.set("scope", scopeName(inChain ? viewed : next));
        if (inChain && next.level !== viewed.level) updated.set("level", next.level);
        else updated.delete("level");
        setParams(updated);
      }} />
  </section>;
}

function SettingsTarget({ target, known, visibleReport, onSelect }: {
  target: SettingsScope;
  known: ReadonlyMap<SettingsLevel, SettingsScope>;
  visibleReport: ExplainReport | undefined;
  onSelect(scope: SettingsScope, inChain: boolean): void;
}) {
  const schema = useSettingsSchema(target);
  const explain = useSettingsExplain(target);
  const entries = useSettingsEntries(target);
  const failure = schema.error ?? explain.error ?? entries.error;
  const chooser = (disabled: boolean) => <LevelPicker current={target} known={known} disabled={disabled} onSelect={onSelect} />;

  return <>
    {failure && <ErrorPanel error={failure} onRetry={() => {
      void schema.refetch(); void explain.refetch(); void entries.refetch();
    }} />}
    {schema.data && explain.data && entries.data ? <SettingsEditor
      target={target} known={known} schema={schema.data} explain={explain.data} visibleReport={visibleReport ?? explain.data}
      snapshot={entries.data} chooser={chooser} unavailable={Boolean(failure)}
      reading={schema.isFetching || explain.isFetching || entries.isFetching}
      reload={async () => {
        const [rows, report] = await Promise.all([entries.refetch(), explain.refetch()]);
        return rows.isSuccess && report.isSuccess ? rows.data : undefined;
      }}
    /> : <>
      {chooser(false)}
      {!failure && <Spinner label="Загрузка настроек…" />}
    </>}
  </>;
}

type RowIntent = {
  key: string;
  base: BaseRow | null;
  generation: number;
  op: DraftOp | { op: "lock" | "unlock" };
};

function SettingsEditor({ target, known, schema, explain, visibleReport, snapshot, chooser, unavailable, reading, reload }: {
  target: SettingsScope;
  known: ReadonlyMap<SettingsLevel, SettingsScope>;
  schema: GetSchemaView;
  explain: ExplainReport;
  visibleReport: ExplainReport;
  snapshot: EntriesSnapshot;
  chooser(disabled: boolean): React.ReactNode;
  unavailable: boolean;
  reading: boolean;
  reload(): Promise<EntriesSnapshot | undefined>;
}) {
  const rights = useSettingsPermissions(target);
  const refresh = useRefreshSettings();
  const [sectionId, setSection] = useState("");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<Draft>();
  const [preview, setPreview] = useState<{ draft: Draft; generation: number }>();
  const [importOpen, setImportOpen] = useState(false);
  const [row, setRow] = useState<RowIntent>();
  const [submittedPreview, setSubmittedPreview] = useState<typeof preview>();
  const [submittedRow, setSubmittedRow] = useState<RowIntent>();
  const [forcedConflict, setForcedConflict] = useState(false);
  const [conflictLoading, setConflictLoading] = useState(false);
  const [conflictRead, setConflictRead] = useState<{ before: EntriesSnapshot; current: EntriesSnapshot }>();
  const [dismissed, setDismissed] = useState<EntriesSnapshot>();
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState("");

  const { sections, registry, specs } = useMemo(() => {
    const sections = schema.sections.map((section) => ({
      id: section.id, title: section.title, keys: section.keys.map((key) => schemaKey(key, section.schema)),
    }));
    return {
      sections,
      registry: Object.fromEntries([
        ...bundledSchemas.map((document) => [document.$id, document]),
        ...schema.sections.map((section) => [section.schema_urn, section.schema]),
      ]),
      specs: new Map(sections.flatMap(({ keys }) => keys.map((spec) => [spec.key, spec] as const))),
    };
  }, [schema]);
  const currentSnapshot = conflictRead?.before === snapshot ? conflictRead.current : snapshot;
  const base = startDraft(target, currentSnapshot, specs.keys());
  const reports = new Map(explain.keys.map((report) => [report.key, report]));
  const visible = new Map(visibleReport.keys.map((report) => [report.key, report]));
  const scopedWriter = canWriteScope(target.level, rights);
  const writable = (spec: KeySpec) => canWrite(target, rights, spec, reports.get(spec.key));
  const canLock = (spec: KeySpec) => writable(spec) && spec.lockable && rights.has("config.lock") &&
    (target.level === "instance" || target.level === "workspace");
  const busy = unavailable || refreshing || conflictLoading;
  const blocked = busy || reading;
  const stale = !!draft && (forcedConflict || draftIsStale(draft, currentSnapshot));
  const loneLock = row?.op.op === "lock" || row?.op.op === "unlock";
  const currentRow = row ? base.base[row.key] ?? null : null;
  const lockStale = loneLock && !!row && (forcedConflict || !sameRowVersion(row.base, currentRow));
  const hasSubmission = (preview && submittedPreview === preview) || (row && submittedRow === row);
  const showConflict = (stale || lockStale) && !hasSubmission && !busy &&
    dismissed !== currentSnapshot;
  const chosen = filterSections(sections, search);
  const active = chosen.find(({ id }) => id === sectionId) ?? chosen[0];
  const groups = new Map<string, KeySpec[]>();
  for (const spec of active?.keys ?? []) {
    const keys = groups.get(spec.ui.group) ?? [];
    keys.push(spec);
    groups.set(spec.ui.group, keys);
  }
  const safeValue = (key: string, value: unknown) => safeSettingValue(specs.get(key), registry, value);

  const previewPolicy: PreviewPolicy = {
    safeValue,
    mayChange: ({ key, before, after }) => {
      const spec = specs.get(key);
      const changedLock = (own(before, "locked") === true) !== (own(after, "locked") === true);
      return !!spec && writable(spec) && (!changedLock || canLock(spec));
    },
    needsConfirmation: (key) => specs.get(key)?.confirm === true,
    problemMessage: (problem) => {
      const spec = problem.key ? specs.get(problem.key) : undefined;
      return spec && (spec.sensitivity === "secret" || schemaTouchesSecret(spec.value_schema, registry, []))
        ? "Сервер отклонил значение" : problem.message;
    },
  };

  const invalid = draft && [...draft.ops].some(([key, op]) => {
    const spec = specs.get(key);
    return !spec || !writable(spec) || ("value" in op && op.value === undefined);
  });
  const separateRemoval = !!draft && [...draft.ops.values()].some(({ op }) => op === "remove") &&
    (currentSnapshot.hasUnexported || currentSnapshot.entries.some((entry) => {
      if (draft.ops.get(entry.key)?.op === "remove") return false;
      const spec = specs.get(entry.key);
      return !spec || !writable(spec) || (entry.locked && !canLock(spec));
    }));

  function edit(key: string, operation?: DraftOp) {
    if (refreshing || (operation && (busy || stale))) return;
    setNotice("");
    setDraft((previous) => {
      const next = setDraftOp(previous ?? base, key, operation);
      return next.ops.size ? next : undefined;
    });
  }

  function onConflict() {
    setPreview(undefined);
    setSubmittedPreview(undefined);
    setSubmittedRow(undefined);
    if (!loneLock) setRow(undefined);
    setDismissed(undefined);
    setForcedConflict(true);
    setConflictLoading(true);
    void reload().then((latest) => {
      if (latest) setConflictRead({ before: snapshot, current: latest });
      else setNotice("Не удалось получить текущие записи. Повторите обновление.");
      setConflictLoading(false);
    });
  }

  function applied(clearDraft: boolean) {
    setNotice("Настройки сохранены.");
    setPreview(undefined);
    setImportOpen(false);
    setRow(undefined);
    setSubmittedPreview(undefined);
    setSubmittedRow(undefined);
    setRefreshing(true);
    if (draft && row?.op.op === "remove") {
      const remaining = setDraftOp(draft, row.key);
      setDraft(remaining.ops.size ? remaining : undefined);
      if (remaining.ops.size) {
        void reload().then((latest) => {
          const next = latest && startDraft(target, latest, specs.keys());
          const otherRows = new Set([...Object.keys(remaining.base), ...Object.keys(next?.base ?? {})]);
          otherRows.delete(row.key);
          if (next && !next.base[row.key] && [...otherRows].every((key) =>
            sameRowVersion(remaining.base[key] ?? null, next.base[key] ?? null))) {
            setDraft(rebase(remaining, next, new Set()));
          } else {
            setForcedConflict(true);
          }
        }).finally(() => void refresh().finally(() => setRefreshing(false)));
        return;
      }
    }
    if (clearDraft) setDraft(undefined);
    void refresh().finally(() => setRefreshing(false));
  }

  function closeConflict() {
    setPreview(undefined);
    setDismissed(currentSnapshot);
    if (loneLock) {
      setRow(undefined);
      setForcedConflict(false);
    }
  }

  function resolve(takeCurrent: ReadonlySet<string>) {
    if (blocked) return;
    if (draft) {
      const next = rebase(draft, base, takeCurrent);
      setDraft(next.ops.size ? next : undefined);
    }
    if (row && loneLock) {
      const desired = row.op.op === "lock";
      setRow(currentRow && currentRow.locked !== desired && !takeCurrent.has(row.key) ?
        { ...row, base: currentRow, generation: explain.generation } : undefined);
    } else {
      setRow(undefined);
    }
    setDismissed(undefined);
    setForcedConflict(false);
    setPreview(undefined);
    setNotice("");
  }

  function renderRow(spec: KeySpec) {
    const row = (draft ?? base).base[spec.key] ?? null;
    const operation = draft?.ops.get(spec.key);
    return <KeyRow key={spec.key} spec={spec} target={target} known={known} base={row} operation={operation}
      effective={visible.get(spec.key) ?? reports.get(spec.key)} targetReport={reports.get(spec.key)} registry={registry}
      writable={!busy && !stale && writable(spec)} lockable={!busy && !draft && canLock(spec)}
      canSave={!!operation && !blocked && !stale &&
        (operation.op === "remove" && separateRemoval || draft?.ops.size === 1 && !invalid)}
      onEdit={(op) => edit(spec.key, op)}
      onSave={() => { if (operation) setRow({ key: spec.key, base: row, op: operation, generation: explain.generation }); }}
      onLock={() => {
        if (row) setRow({ key: spec.key, base: row, op: { op: row.locked ? "unlock" : "lock" }, generation: explain.generation });
      }} />;
  }

  const conflictRows = loneLock && row?.base ? [
    compareRow(row.key, row.base, currentRow, { ...row.base, locked: row.op.op === "lock" }),
  ] : draft ? compareDraft(draft, base) : [];
  const rowSpec = row ? specs.get(row.key) : undefined;

  return <>
    {chooser(Boolean(draft || row || importOpen || refreshing))}
    <ExportButton scope={target} />
    {scopedWriter && <Button disabled={!!draft || !!row || blocked} onClick={() => setImportOpen(true)}>Импорт</Button>}
    {!scopedWriter && <p>Область доступна для чтения.</p>}
    <SectionTree sections={chosen} active={active?.id} search={search} onSearch={setSearch} onSelect={setSection}
      isLocked={(key) => !!(reports.get(key)?.locked_by || base.base[key]?.locked)} />
    {active ? <section aria-label={escapeText(active.title)}>
      <h2>{escapeText(active.title)}</h2>
      {[...groups].map(([group, keys]) => {
        const sorted = [...keys].sort((left, right) => left.ui.order - right.ui.order);
        const advanced = sorted.filter((key) => key.ui.advanced);
        return <section key={group}>
          <h3>{escapeText(group)}</h3>
          {sorted.filter((key) => !key.ui.advanced).map(renderRow)}
          {advanced.length > 0 && <details open={search.trim() ? true : undefined}>
            <summary>Advanced ({advanced.length})</summary>
            {advanced.map(renderRow)}
          </details>}
        </section>;
      })}
    </section> : <p>Подходящих настроек нет.</p>}
    {notice && <p role="status">{notice}</p>}
    {draft && <section aria-label="Черновик">
      <p>Изменений в черновике: {draft.ops.size}</p>
      {invalid && <p>Проверьте значения и доступ к изменяемым ключам.</p>}
      {separateRemoval && <p>Сохраните удаление отдельно, затем проверьте оставшиеся изменения.</p>}
      {stale && <Button disabled={conflictLoading} onClick={onConflict}>Проверить конфликт</Button>}{" "}
      <Button disabled={refreshing} onClick={() => {
        setDraft(undefined); setForcedConflict(false); setDismissed(undefined); setNotice("");
      }}>Отменить черновик</Button>{" "}
      <Button disabled={blocked || stale || invalid || separateRemoval}
        onClick={() => setPreview({ draft, generation: explain.generation })}>Предпросмотр</Button>
    </section>}
    {preview && !showConflict && <PreviewDialog request={draftImport(preview.draft)}
      policy={{
        ...previewPolicy,
        mayChange: (change) => preview.draft.ops.has(change.key) && previewPolicy.mayChange(change),
      }}
      simulateConfirmation={[...preview.draft.ops.keys()].some(previewPolicy.needsConfirmation)}
      stale={stale || draft !== preview.draft || explain.generation !== preview.generation}
      blocked={blocked} casChanged={preview.draft.entriesDigest !== currentSnapshot.digest}
      onSubmit={() => setSubmittedPreview(preview)}
      onClose={() => { setPreview(undefined); setSubmittedPreview(undefined); }}
      onConflict={onConflict} onApplied={() => applied(true)} />}
    {importOpen && <ImportDialog scope={target} snapshot={snapshot} generation={explain.generation}
      blocked={blocked || !scopedWriter} policy={previewPolicy}
      onClose={() => setImportOpen(false)} onApplied={() => applied(false)} reload={reload} />}
    {row && rowSpec && !showConflict && !conflictLoading && <RowWriteDialog intent={row} spec={rowSpec} scope={target}
      stale={stale || lockStale || row.generation !== explain.generation}
      blocked={blocked || (loneLock ? !canLock(rowSpec) : !writable(rowSpec))}
      casChanged={row.base?.row_version !== currentRow?.row_version}
      onSubmit={() => setSubmittedRow(row)}
      onClose={() => { setRow(undefined); setSubmittedRow(undefined); }}
      onConflict={onConflict} onApplied={() => applied(!loneLock)} />}
    {showConflict && <ConflictView key={`${currentSnapshot.digest}:${conflictRows
      .map(({ current }) => `${current?.entry_id}/${current?.row_version}`).join(",")}`}
      rows={conflictRows} safeValue={safeValue} disabled={blocked} onClose={closeConflict} onRebase={resolve} />}
  </>;
}

function RowWriteDialog({ intent, spec, scope, stale, blocked, casChanged, onClose, onConflict, onApplied, onSubmit }: {
  intent: RowIntent;
  spec: KeySpec;
  scope: SettingsScope;
  stale: boolean;
  blocked: boolean;
  casChanged: boolean;
  onClose(): void;
  onConflict(): void;
  onApplied(): void;
  onSubmit(): void;
}) {
  const { transport } = useAuth();
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const action = intent.op.op;
  const lock = action === "lock" || action === "unlock";
  const title = action === "lock" ? "Заблокировать" : action === "unlock" ? "Разблокировать" : "Сохранить ключ";
  const mutation = useIdempotentMutation(async (command: RowWrite, key) => {
    try {
      await writeSetting(transport, command, key);
      onApplied();
    } catch (error) {
      if (isSettingsConflict(error)) onConflict();
      throw error;
    }
  });
  const pending = mutation.status === "pending";
  const submitted = mutation.status !== "idle";
  const disabled = blocked || stale;
  const canRetry = mutation.error instanceof ApiError && (mutation.error.status === 0 || mutation.error.status >= 500) &&
    !blocked && (!stale || casChanged);

  return <Dialog open title={`${title} · ${spec.key}`} onClose={() => { if (!pending) onClose(); }}>
    <form onSubmit={(event) => {
      event.preventDefault();
      if (disabled || submitted || (spec.confirm && !confirmed) || (lock && !reason.trim())) return;
      const command = { scope, key: intent.key, reason: reason.trim(), confirmed };
      const version = intent.base?.row_version ?? null;
      onSubmit();
      if ("value" in intent.op) mutation.submit({ ...command, ...intent.op, version });
      else if (action === "unset") mutation.submit({ ...command, op: action, version });
      else if (version !== null && (action === "remove" || lock)) mutation.submit({ ...command, op: action, version });
    }}>
      <p>Операция <code>{action}</code></p>
      {stale && <p role="alert">Запись устарела. Обновите данные перед сохранением.</p>}
      <label>Причина <input value={reason} maxLength={2000} required={lock} disabled={submitted}
        onChange={(event) => setReason(event.currentTarget.value)} /></label>
      {spec.confirm && <label>
        <input type="checkbox" checked={confirmed} disabled={submitted}
          onChange={(event) => setConfirmed(event.currentTarget.checked)} /> Подтверждаю изменение
      </label>}
      <Button type="submit" disabled={disabled || submitted || (spec.confirm && !confirmed) || (lock && !reason.trim())}>
        {title}
      </Button>
      {mutation.error && <ErrorPanel error={mutation.error} {...(canRetry ? {
        onRetry: () => { if (canRetry) mutation.retry(); },
      } : {})} />}
    </form>
  </Dialog>;
}
