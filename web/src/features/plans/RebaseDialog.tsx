import { useState } from "react";
import { ApiError } from "../../api/errors";
import type { RebaseDraftResult } from "../../api/generated/planning";
import { useRebaseDraft, type DraftRebase } from "../../api/hooks/planning";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";
import { isRecord } from "../../components/schema-form/values";
import { escapeText } from "../../lib/safeText";
import { fieldIssues } from "./EntityEditor";

type Resolution = NonNullable<DraftRebase["resolutions"]>[number];
type Conflict = Record<string, unknown> & { conflict_id: string; resolutions: readonly unknown[] };

function readConflicts(error: unknown) {
  if (!(error instanceof ApiError) || error.code !== "REBASE_CONFLICTS") return;
  const { conflicts, current_revision_id, edit_version } = error.details;
  if (!Array.isArray(conflicts) || typeof current_revision_id !== "string" || typeof edit_version !== "number") return;
  return {
    onto: current_revision_id as NonNullable<DraftRebase["onto_revision_id"]>,
    version: edit_version,
    rows: conflicts.filter((row): row is Conflict =>
      isRecord(row) && typeof row.conflict_id === "string" && Array.isArray(row.resolutions)),
  };
}

export function RebaseDialog({ planId, draftId, version, onClose, onSuccess }: {
  planId: string; draftId: string; version: number; onClose(): void; onSuccess(result: RebaseDraftResult): void;
}) {
  const rebase = useRebaseDraft(planId, draftId);
  const [lastError, setLastError] = useState<unknown>(null);
  const [conflicts, setConflicts] = useState<ReturnType<typeof readConflicts>>();
  const [choices, setChoices] = useState<Record<string, string>>({});
  if (rebase.error !== lastError) {
    setLastError(rebase.error);
    const report = readConflicts(rebase.error);
    if (report) {
      const sameBase = conflicts?.onto === report.onto && conflicts.version === report.version;
      setConflicts(sameBase ? {
        ...report,
        rows: [...conflicts.rows.filter((row) => row.kind !== "schema" &&
          !report.rows.some((updated) => updated.conflict_id === row.conflict_id)), ...report.rows],
      } : report);
      if (!sameBase) setChoices({});
    }
  }

  const expired = !!conflicts && (conflicts.version !== version ||
    (rebase.error instanceof ApiError && rebase.error.code === "BASE_REVISION_CHANGED"));
  const resolutions = conflicts?.rows.flatMap((row): Resolution[] => {
    const choice = choices[row.conflict_id]?.trim();
    if (!choice) return [];
    return row.resolutions.includes("rekey") ? [{ conflict_id: row.conflict_id, new_key: choice }]
      : choice === "yours" || choice === "theirs" ? [{ conflict_id: row.conflict_id, keep: choice }] : [];
  }) ?? [];
  const fieldsToResolve = conflicts?.rows.filter((row) => row.resolutions.length > 0).length;
  const ready = !conflicts || (resolutions.length === fieldsToResolve && (!!fieldsToResolve || !conflicts.rows.length));

  function submit() {
    rebase.mutate({
      expected_edit_version: version,
      ...(conflicts ? { onto_revision_id: conflicts.onto, resolutions } : {}),
    }, { onSuccess });
  }

  return <Dialog open title="Rebase черновика" onClose={() => { if (!rebase.isPending) onClose(); }}>
    <p>Перенести сохранённую версию v{version} на текущую ревизию плана.</p>
    {rebase.error && !readConflicts(rebase.error) && <ErrorPanel error={rebase.error} />}
    {conflicts && <>
      <p role="status">Конфликты с ревизией {escapeText(conflicts.onto)}</p>
      <Table rows={conflicts.rows} rowKey={(row) => row.conflict_id} columns={[
        { id: "field", header: "Поле", cell: (row) => <>
          {escapeText([row.key, row.field, row.pointer].filter((part) => typeof part === "string").join(" · ") || String(row.kind))}
          {fieldIssues(row.issues).map((issue, i) => <p key={i}>{escapeText(issue.pointer)} · {escapeText(issue.message)}</p>)}
        </> },
        ...(["base", "yours", "theirs"] as const).map((side) => ({
          id: side, header: side, cell: (row: Conflict) => <code>{escapeText(JSON.stringify(row[side]) ?? "—")}</code>,
        })),
        { id: "resolution", header: "Решение", cell: (row) => {
          const label = `Решение · ${escapeText(String(row.key ?? row.field ?? row.conflict_id))}`;
          const value = choices[row.conflict_id] ?? "";
          const change = (next: string) => setChoices({ ...choices, [row.conflict_id]: next });
          if (row.resolutions.includes("rekey")) {
            return <label>{label} <input placeholder="Новый ключ" value={value} disabled={rebase.isPending || expired}
              onChange={(event) => change(event.target.value)} /></label>;
          }
          if (!row.resolutions.length) return "Исправьте черновик перед переносом";
          return <label>{label} <select value={value} disabled={rebase.isPending || expired} onChange={(event) => change(event.target.value)}>
            <option value="">Выберите значение</option>
            {row.resolutions.includes("yours") && <option value="yours">Ваше</option>}
            {row.resolutions.includes("theirs") && <option value="theirs">Текущее</option>}
          </select></label>;
        } },
      ]} />
    </>}
    {expired ? <Button onClick={() => {
      rebase.reset();
      setConflicts(undefined);
      setChoices({});
    }}>Заново проверить конфликты</Button>
      : <Button disabled={rebase.isPending || !ready} onClick={submit}>{conflicts ? "Применить решения" : "Начать rebase"}</Button>}
  </Dialog>;
}
