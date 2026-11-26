import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import { ApiError } from "../../api/errors";
import type { DraftView, PlanView, SaveDraftDefsDraftChange, SaveDraftResult } from "../../api/generated/planning";
import { planPath, useDraft, useDraftSavedVersion, usePlan, usePlanPermissions, useSaveDraft, useValidateDraft, type DraftSave } from "../../api/hooks/planning";
import { useScope } from "../../app/providers/ScopeProvider";
import { SafeLink } from "../../components/content/SafeLink";
import { EmptyState } from "../../components/data/EmptyState";
import { ConflictPanel } from "../../components/feedback/ConflictPanel";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";
import { Skeleton } from "../../components/primitives/Skeleton";
import { appendPointer, isRecord, jsonEqual, own, pointerTokens, removeAtPointer, setAtPointer } from "../../components/schema-form/values";
import { Tree, type TreeNode } from "../../components/viz/Tree";
import { escapeText } from "../../lib/safeText";
import { EntityEditor, entityKinds, fieldIssues, type EntityList, type EntityValue } from "./EntityEditor";
import { FindingsPanel, type Finding } from "./FindingsPanel";
import { PublishDialog } from "./PublishDialog";
import { RebaseDialog } from "./RebaseDialog";

const SimulatePanel = lazy(() => import("./SimulatePanel"));

const lists = Object.keys(entityKinds) as EntityList[];
const addActions = [
  ["phases", "Phase"], ["items", "Item"], ["units", "Unit"], ["checks", "Check"],
  ["decisions", "Decision"], ["requirements", "Requirement"],
] as const;
type AddList = typeof addActions[number][0];
type Entity = { id: string; list: EntityList; value: EntityValue };
type Row = Entity & { pointer: string; saved?: EntityValue };
type WorkingCopy = { base: DraftView; edits: ReadonlyMap<string, EntityValue>; added: readonly Entity[] };
type FieldConflict = { row: Row; pointer: string; base: unknown; yours: unknown; theirs: unknown };
type Submission = { input: DraftSave; rowIds: ReadonlyMap<string, string> };
type Rekey = Extract<SaveDraftDefsDraftChange, { op: "rekey" }>;

function displayKey(list: EntityList, value: EntityValue) {
  const key = String(value.key ?? "");
  if (list === "checks") return `${String(value.owner ?? "")}:${key}`;
  return list === "materials" ? `material/${key}` : key;
}

function rowsFor(draft: DraftView, working?: WorkingCopy | null): Row[] {
  return lists.flatMap((list) => {
    const saved = (draft.document[list] ?? []).map((entity, index): Row => {
      const pointer = `/${list}/${index}`;
      const id = entity.id ?? pointer;
      const value = { ...entity };
      return { id, list, pointer, value: working?.edits.get(id) ?? value, saved: value };
    });
    const added = working?.added.filter((entry) => entry.list === list) ?? [];
    return [...saved, ...added.map((entry, index) => ({ ...entry, pointer: `/${list}/${saved.length + index}` }))];
  });
}

function changed(row: Row) {
  return !row.saved || !jsonEqual(row.saved, row.value);
}

function planTree(rows: readonly Row[], selected: string | undefined): TreeNode[] {
  const children = new Map<string, TreeNode[]>();
  const containers = new Set(rows.filter((row) => row.list === "phases" || row.list === "items")
    .map((row) => displayKey(row.list, row.saved ?? row.value)));
  const roots: TreeNode[] = [];
  // Assemble children first so each phase and item can include its descendants.
  for (const row of [...rows].reverse()) {
    const value = row.saved ?? row.value;
    const key = displayKey(row.list, value);
    const title = row.value.title;
    const parent = row.list === "items" ? value.phase : row.list === "units" ? key.split("/")[0]
      : row.list === "checks" || row.list === "criteria" ? value.owner : undefined;
    const node = {
      id: row.id,
      label: [key || entityKinds[row.list], ...(typeof title === "string" && title ? [title] : [])].join(" · ")
        + (changed(row) ? " *" : ""),
      ...(children.has(key) ? { children: children.get(key)! } : {}),
      ...(row.id === selected ? { status: "Выбрано" } : {}),
    };
    if (typeof parent === "string" && containers.has(parent)) {
      const siblings = children.get(parent) ?? [];
      siblings.unshift(node);
      children.set(parent, siblings);
    } else roots.unshift(node);
  }
  return roots;
}

function nextKey(rows: readonly Row[], list: EntityList, prefix: string, owner?: string) {
  const used = new Set(rows.filter((row) => row.list === list && (owner === undefined || row.value.owner === owner))
    .flatMap((row) => [row.value.key, row.saved?.key]));
  let index = 1;
  while (used.has(prefix + index)) index += 1;
  return prefix + index;
}

function skeleton(list: AddList, rows: readonly Row[], selection: Row | undefined): EntityValue {
  const context = selection?.saved ?? selection?.value;
  const selectedItem = selection?.list === "items" ? context?.key
    : selection?.list === "units" ? String(context?.key ?? "").split("/")[0]
    : selection?.list === "checks" || selection?.list === "criteria" ? context?.owner : undefined;
  const item = rows.find((row) => row.list === "items" && (row.saved ?? row.value).key === selectedItem)
    ?? rows.find((row) => row.list === "items");
  const phase = selection?.list === "phases" ? context?.key : (item?.saved ?? item?.value)?.phase;
  const phaseKey = String(phase ?? (rows.find((row) => row.list === "phases")?.value.key) ?? "P1");
  const itemKey = String((item?.saved ?? item?.value)?.key ?? phaseKey + ".1");
  switch (list) {
    case "phases": return { key: nextKey(rows, list, "P"), title: "Новая фаза", goal: "Цель фазы", design_state: "skeleton" };
    case "items": return {
      key: nextKey(rows, list, phaseKey + "."), phase: phaseKey, title: "Новый пункт",
      summary: "Описание работы", why: "Обоснование", review: { mode: "required" },
    };
    case "units": return { key: nextKey(rows, list, itemKey + "/U"), title: "Новая единица работы", goal: "Цель работы" };
    case "checks": {
      const owner = selection?.list === "phases" || !item ? phaseKey : itemKey;
      return { key: nextKey(rows, list, "V", owner), owner, category: "acceptance", kind: "manual",
        definition: { instructions_md: "Условия проверки", actor_role: "maintainer" } };
    }
    case "decisions": return { key: nextKey(rows, list, "D"), title: "Новое решение", state: "open" };
    case "requirements": return {
      key: nextKey(rows, list, "R"), statement: "Новое требование", priority: "must", source: { kind: "owner" },
    };
  }
}

function mergePatch(before: EntityValue, after: EntityValue): EntityValue {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  return Object.fromEntries([...keys].flatMap((key) => {
    const previous = own(before, key), value = own(after, key);
    if (jsonEqual(previous, value)) return [];
    return [[key, value === undefined ? null : isRecord(previous) && isRecord(value) ? mergePatch(previous, value) : value]];
  }));
}

function mergeFields(base: unknown, yours: unknown, theirs: unknown, pointer: string,
  conflict: (issue: Omit<FieldConflict, "row">) => void): unknown {
  if (jsonEqual(yours, base)) return theirs;
  if (jsonEqual(theirs, base) || jsonEqual(yours, theirs)) return yours;
  if ((base === undefined || isRecord(base)) && isRecord(yours) && isRecord(theirs)) {
    const keys = new Set([...Object.keys(yours), ...Object.keys(theirs)]);
    const merged: [string, unknown][] = [];
    for (const key of keys) {
      const value = mergeFields(own(base, key), own(yours, key), own(theirs, key), appendPointer(pointer, key), conflict);
      if (value !== undefined) merged.push([key, value]);
    }
    return Object.fromEntries(merged);
  }
  conflict({ pointer, base, yours, theirs });
  return yours;
}

function retarget(working: WorkingCopy, draft: DraftView) {
  const latest = new Map(rowsFor(draft).map((row) => [row.id, row.value]));
  const edits = new Map<string, EntityValue>();
  const conflicts: FieldConflict[] = [];
  for (const row of rowsFor(working.base, working)) {
    if (!row.saved || !changed(row)) continue;
    const value = latest.get(row.id);
    if (!value) return null;
    const merged = mergeFields(row.saved, row.value, value, "", (issue) => conflicts.push({ ...issue, row }));
    if (isRecord(merged) && !jsonEqual(merged, value)) edits.set(row.id, merged);
  }
  return { working: { ...working, base: draft, edits }, conflicts };
}

function orderedRekeys(rows: readonly Row[], document: DraftView["document"]): Rekey[] {
  const result: Rekey[] = [];
  const reserved = JSON.stringify([document, rows.map((row) => row.value)]);
  const keys = new Set(rows.flatMap((row) => [displayKey(row.list, row.value), displayKey(row.list, row.saved ?? row.value)]));
  let suffix = 0;
  // Descendants go first because a phase or item rekey also renames its descendants.
  for (const list of [...lists].reverse()) {
    const pending = rows.flatMap((row): Rekey[] => row.list === list && row.saved && row.saved.key !== row.value.key
      ? [{ op: "rekey", target: displayKey(list, row.saved), new_key: displayKey(list, row.value) }] : []);
    while (pending.length) {
      const occupied = new Set(pending.map((change) => change.target));
      const ready = pending.findIndex((change) => !occupied.has(change.new_key));
      if (ready !== -1) {
        result.push(pending.splice(ready, 1)[0]!);
        continue;
      }
      // Every remaining destination is occupied by another pending rename. Break a cycle with a free key of the same kind.
      const change = pending[0]!;
      const prefix = list === "materials" ? "material/draft-tmp-" : change.target.replace(/\d+$/u, "") + "900000";
      let temporary: string;
      do {
        suffix += 1;
        temporary = prefix + suffix;
      } while (keys.has(temporary) || reserved.includes(temporary));
      keys.add(temporary);
      result.push({ ...change, new_key: temporary });
      pending[0] = { ...change, target: temporary };
    }
  }
  return result;
}

function submittedRows(rows: readonly Row[], typed: boolean) {
  return new Map(lists.flatMap((list) => {
    const entries = rows.filter((row) => row.list === list);
    if (!typed || (list !== "items" && list !== "units")) return entries.map((row) => [row.pointer, row.id] as const);
    const group = (value: EntityValue) => list === "items" ? value.phase : String(value.key ?? "").split("/")[0];
    const ordered = entries.filter((row) => row.saved);
    // POST /changes inserts each add after the last item in its phase or unit in its item.
    for (const row of entries.filter((entry) => !entry.saved)) {
      const last = ordered.map((entry) => group(entry.saved ?? entry.value)).lastIndexOf(group(row.value));
      ordered.splice(last < 0 ? ordered.length : last + 1, 0, row);
    }
    return ordered.map((row, index) => [`/${list}/${index}`, row.id] as const);
  }));
}

function saveInput(rows: readonly Row[], base: DraftView): Submission {
  const dirty = rows.filter(changed);
  const expected_edit_version = base.edit_version;
  const renames = dirty.some((row) => row.saved && row.saved.key !== row.value.key) ? orderedRekeys(rows, base.document) : [];
  const edits: SaveDraftDefsDraftChange[] = dirty.flatMap((row): SaveDraftDefsDraftChange[] => {
    if (!row.saved) return [{ op: "add", kind: entityKinds[row.list], entity: row.value }];
    const patch = mergePatch(row.saved, row.value);
    delete patch.key;
    delete patch.id;
    return Object.keys(patch).length ? [{ op: "patch", target: displayKey(row.list, row.saved), merge_patch: patch }] : [];
  });
  function hasDeletion(value: unknown): boolean {
    return value === null || (isRecord(value) && Object.values(value).some(hasDeletion));
  }
  if (renames.length || edits.some((change) => change.op === "patch" && hasDeletion(change.merge_patch.work_policy))) {
    return { input: { expected_edit_version, changes: [...edits, ...renames] }, rowIds: submittedRows(rows, true) };
  }
  const touched = new Set(dirty.map((row) => row.list));
  const merge_patch = Object.fromEntries([...touched].map((list) => [list, rows.filter((row) => row.list === list).map((row) => row.value)]));
  return { input: { expected_edit_version, merge_patch }, rowIds: submittedRows(rows, false) };
}

function DraftEditor({ plan, draft, eventsCursor, reload, readError }: {
  plan: PlanView; draft: DraftView; eventsCursor: number | undefined; reload(): Promise<DraftView | undefined>; readError: unknown;
}) {
  const planId = plan.plan_id;
  const draftId = draft.draft_id;
  const permissions = usePlanPermissions("plan", planId);
  const save = useSaveDraft(planId, draftId);
  const [working, setWorking] = useState<WorkingCopy | null>(null);
  const [selectedId, setSelectedId] = useState<string>();
  const [focus, setFocus] = useState<{ pointer: string } | null>(null);
  const [acceptedVersion, setAcceptedVersion] = useState(draft.edit_version);
  const [adoptVersion, setAdoptVersion] = useState<number>();
  const [fieldConflicts, setFieldConflicts] = useState<readonly FieldConflict[]>([]);
  const [lostEntity, setLostEntity] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [simulateOpen, setSimulateOpen] = useState(false);
  const [rebaseOpen, setRebaseOpen] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const [submitted, setSubmitted] = useState<Submission>();
  const [snapshotCursor] = useState(eventsCursor);
  const announcedVersion = useDraftSavedVersion(planId, draftId, snapshotCursor);
  const requiredVersion = Math.max(acceptedVersion, announcedVersion, adoptVersion ?? 0);
  const snapshotBehind = draft.edit_version < requiredVersion;
  useEffect(() => {
    if (!snapshotBehind || readError) return;
    // The workspace feed triggers a refetch. Keep retrying while GET still trails the announced version.
    const timer = setInterval(() => { void reload(); }, 1000);
    return () => clearInterval(timer);
  }, [snapshotBehind, readError, reload]);

  if (adoptVersion !== undefined && !snapshotBehind) {
    setAdoptVersion(undefined);
    setAcceptedVersion(draft.edit_version);
    if (working) {
      const adopted = retarget(working, draft);
      if (adopted) {
        setWorking(adopted.working.edits.size || adopted.working.added.length ? adopted.working : null);
        setFieldConflicts(adopted.conflicts);
      }
      setLostEntity(!adopted);
    }
  }

  const version = Math.max(requiredVersion, draft.edit_version);
  const base = working?.base ?? draft;
  const rows = rowsFor(base, working);
  const selected = rows.find((row) => row.id === selectedId) ?? rows[0];
  const dirty = rows.some(changed);
  const ready = !snapshotBehind && adoptVersion === undefined;
  const resolving = fieldConflicts.length > 0;
  const open = draft.state === "open" && plan.lifecycle_state === "active";
  const canEdit = open && permissions.has("plan.edit");
  const canPreview = open && permissions.has("plan.publish") && !dirty && ready && !save.isPending;
  const foreign = version > acceptedVersion || (dirty && version > base.edit_version);
  const outdatedBase = draft.stale || (plan.current_revision_id ?? null) !== draft.base_revision_id;
  const validation = useValidateDraft(planId, { draftId, expectedEditVersion: version }, open && ready);
  const report = validation.data?.edit_version === version && base.edit_version === version ? validation.data : undefined;
  const problem = save.error instanceof ApiError ? save.error : undefined;
  const conflict = problem?.code === "VERSION_CONFLICT" || problem?.code === "BASE_REVISION_CHANGED";
  const issues = problem?.status === 422 && problem.code === "SCHEMA_INVALID" ? fieldIssues(problem.details.issues) : [];
  const displayedIssues = [];
  const documentIssues = [];
  const rowsById = new Map(rows.map((row) => [row.id, row]));
  const submittedRowsByPointer = submitted?.input === save.variables ? submitted?.rowIds : undefined;
  for (const issue of issues) {
    const segments = pointerTokens(issue.pointer);
    const root = segments && segments.length >= 2 ? issue.pointer.split("/", 3).join("/") : "";
    const id = submittedRowsByPointer?.get(root);
    const row = id === undefined ? undefined : rowsById.get(id);
    if (row) displayedIssues.push({ ...issue, pointer: row.pointer + issue.pointer.slice(root.length) });
    else documentIssues.push(issue);
  }
  for (const issue of fieldIssues(report?.schema_issues)) {
    if (rows.some((row) => row.saved && (issue.pointer === row.pointer || issue.pointer.startsWith(row.pointer + "/")))) {
      displayedIssues.push(issue);
    } else documentIssues.push(issue);
  }

  function select(id: string, pointer?: string) {
    setSelectedId(id);
    setFocus(pointer !== undefined ? { pointer } : null);
  }

  function selectFinding(finding: Finding) {
    const pointer = finding.pointer ?? undefined;
    const row = rows.find((entry) => entry.id === finding.entity_id)
      ?? rows.find((entry) => displayKey(entry.list, entry.saved ?? entry.value) === finding.entity_key)
      ?? rows.find((entry) => pointer === entry.pointer || pointer?.startsWith(entry.pointer + "/"));
    if (row) select(row.id, pointer ?? row.pointer);
  }

  function update(row: Row, value: EntityValue) {
    const copy = working ?? { base, edits: new Map(), added: [] };
    if (row.saved) {
      const edits = new Map(copy.edits);
      if (jsonEqual(row.saved, value)) edits.delete(row.id);
      else edits.set(row.id, value);
      setWorking(edits.size || copy.added.length ? { ...copy, edits } : null);
    } else setWorking({ ...copy, added: copy.added.map((entry) => entry.id === row.id ? { ...entry, value } : entry) });
    setEpoch(epoch + 1);
  }

  function add(list: AddList) {
    const row = { list, id: crypto.randomUUID(), value: skeleton(list, rows, selected) };
    const copy = working ?? { base, edits: new Map(), added: [] };
    setWorking({ ...copy, added: [...copy.added, row] });
    select(row.id);
    setEpoch(epoch + 1);
  }

  function saved(result: SaveDraftResult) {
    if (selected && !selected.saved) {
      const key = displayKey(selected.list, selected.value);
      setSelectedId(result.assigned_ids.find((entry) => entry.display_key === key && entry.entity_kind === entityKinds[selected.list])?.entity_id);
    }
    setWorking(null);
    setAcceptedVersion(result.edit_version);
    setEpoch(epoch + 1);
  }

  function resolveField(issue: FieldConflict, value: unknown) {
    const row = rowsById.get(issue.row.id);
    if (!row) return;
    const updated = value === undefined ? removeAtPointer(row.value, issue.pointer) : setAtPointer(row.value, issue.pointer, value);
    if (isRecord(updated)) update(row, updated);
    setFieldConflicts(fieldConflicts.filter((entry) => entry !== issue));
  }

  async function adoptCurrent() {
    const latest = await reload();
    if (latest) {
      save.reset();
      setAdoptVersion(latest.edit_version);
    }
  }

  return <>
    <h2>{escapeText(draft.document.title)}</h2>
    <p><SafeLink href={planPath(planId)}>{escapeText(plan.alias)}</SafeLink>
      {" · "}v{version} · {draft.base_revision_no === null ? "Без базовой ревизии" : `База r${draft.base_revision_no}`}
      {dirty && " · * Несохранённые изменения"}
    </p>
    {foreign && <p role="status">draft изменён другим пользователем.</p>}
    {outdatedBase && <p role="status">У плана новая базовая ревизия.</p>}
    {lostEntity && <p role="alert">Текущая версия удалила редактируемую сущность. Локальный текст сохранён в форме.</p>}
    {readError ? <ErrorPanel error={readError} onRetry={reload} /> : !ready && <Skeleton />}
    <div className="toolbar">
      <Button disabled={!open || !ready || validation.isFetching} onClick={() => void validation.refetch()}>Validate</Button>
      <Button disabled={!canEdit || !dirty || !ready || save.isPending || lostEntity || resolving}
        onClick={() => {
          const submission = saveInput(rows, base);
          setSubmitted(submission);
          save.mutate(submission.input, { onSuccess: saved });
        }}>Save</Button>
      <Button disabled={!ready || dirty} onClick={() => setSimulateOpen(true)}>Симуляция</Button>
      <Button disabled={!canPreview} onClick={() => setPreviewOpen(true)}>Publish…</Button>
      {(foreign || outdatedBase || conflict) && canEdit && <Button disabled={!ready || save.isPending || resolving}
        onClick={() => setRebaseOpen(true)}>Rebase</Button>}
      {dirty && <Button disabled={save.isPending || !ready} onClick={() => {
        setWorking(null); setAcceptedVersion(version); setLostEntity(false); setFieldConflicts([]); save.reset(); setEpoch(epoch + 1);
      }}>Сбросить локальные правки</Button>}
    </div>
    {simulateOpen && <Dialog open title="Симуляция черновика" onClose={() => setSimulateOpen(false)}>
      <Suspense fallback={<Skeleton />}><SimulatePanel key={version} planId={planId}
        source={{ draftId: draft.draft_id, expectedEditVersion: version }} /></Suspense>
    </Dialog>}
    {conflict && <ConflictPanel error={problem} submitted={save.variables} current={problem.details} onReload={() => void adoptCurrent()} />}
    {resolving && <section aria-label="Конфликты локальных правок">
      <h3>Выберите значения для конфликтующих полей</h3>
      {fieldConflicts.map((issue) => <fieldset key={issue.row.id + issue.pointer} disabled={!ready}>
        <legend>{escapeText(displayKey(issue.row.list, issue.row.saved ?? issue.row.value) + " · " + issue.pointer)}</legend>
        <p>Было <code>{escapeText(JSON.stringify(issue.base) ?? "—")}</code></p>
        <Button onClick={() => resolveField(issue, issue.yours)}>Оставить своё</Button>
        {" "}<code>{escapeText(JSON.stringify(issue.yours) ?? "—")}</code>{" "}
        <Button onClick={() => resolveField(issue, issue.theirs)}>Принять текущее</Button>
        {" "}<code>{escapeText(JSON.stringify(issue.theirs) ?? "—")}</code>
      </fieldset>)}
    </section>}
    {save.error && !conflict && !issues.length && <ErrorPanel error={save.error} />}
    {!open && <p role="status">Черновик закрыт или план архивирован.</p>}
    {!!documentIssues.length && <ul role="alert">{documentIssues.map((issue, i) => <li key={i}>
      {escapeText(issue.pointer || "/")} · {escapeText(issue.message)}
    </li>)}</ul>}
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space)", alignItems: "flex-start" }}>
      <section aria-label="Дерево плана" style={{ flex: "1 1 14rem", minWidth: 0 }}>
        <div className="toolbar">{addActions.map(([list, label]) => <Button key={list}
          disabled={!canEdit || !ready || save.isPending || lostEntity || resolving} onClick={() => add(list)}>+ {label}</Button>)}</div>
        {rows.length ? <Tree nodes={planTree(rows, selected?.id)} onSelect={(node) => select(node.id)} />
          : <EmptyState title="В черновике нет сущностей" />}
      </section>
      {selected && <article style={{ flex: "3 1 24rem", minWidth: 0 }}>
        <h3>{escapeText(displayKey(selected.list, selected.saved ?? selected.value))} · {entityKinds[selected.list]}</h3>
        <EntityEditor key={selected.id} planId={planId} kind={entityKinds[selected.list]} pointer={selected.pointer}
          value={selected.value} focus={focus} issues={displayedIssues} readOnly={!canEdit || !ready || save.isPending || resolving}
          item={selected.list === "units" ? rows.find((row) => row.list === "items" &&
            displayKey(row.list, row.saved ?? row.value) === String(selected.value.key).split("/")[0])?.value : undefined}
          onChange={(value) => update(selected, value)} />
      </article>}
      <div style={{ flex: "1 1 14rem", minWidth: 0 }}>
        {validation.error && <ErrorPanel error={validation.error} onRetry={() => void validation.refetch()} />}
        {report && <FindingsPanel report={report} onSelect={selectFinding} />}
      </div>
    </div>
    {previewOpen && <PublishDialog planId={planId} draftId={draftId} version={version} epoch={epoch}
      canPreview={canPreview} canReplay={permissions.has("plan.publish") && !dirty && ready} onClose={() => setPreviewOpen(false)}
      {...(canEdit ? { onRebase: () => { setPreviewOpen(false); setRebaseOpen(true); } } : {})} />}
    {rebaseOpen && <RebaseDialog planId={planId} draftId={draftId} version={version}
      onClose={() => setRebaseOpen(false)} onSuccess={(result) => {
        setRebaseOpen(false); save.reset(); setEpoch(epoch + 1); setAdoptVersion(result.edit_version);
      }} />}
  </>;
}

export default function DraftEditorPage() {
  const { planId = "", draftId = "" } = useParams();
  const { scope } = useScope();
  const plan = usePlan(planId);
  const owner = plan.data;
  const scoped = !!owner && (!owner.workspace_id || (owner.workspace_id === scope.workspaceId && owner.project_id === scope.projectId));
  const draft = useDraft(planId, draftId, scoped);
  const { refetch } = draft;
  const reload = useCallback(async () => {
    const result = await refetch({ cancelRefetch: false });
    return result.isSuccess ? result.data.data : undefined;
  }, [refetch]);
  return <section>
    <h1>Редактор черновика</h1>
    {owner && draft.data ? <DraftEditor key={`${planId}/${draftId}`} plan={owner} draft={draft.data.data}
      eventsCursor={draft.data.eventsCursor} reload={reload} readError={draft.error ?? plan.error} />
      : plan.error || draft.error ? <ErrorPanel error={plan.error ?? draft.error}
        onRetry={() => { if (plan.error) void plan.refetch(); else void draft.refetch(); }} />
        : <Skeleton />}
  </section>;
}
