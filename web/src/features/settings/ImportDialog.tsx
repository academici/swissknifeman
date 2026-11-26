import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ImportConfig, ImportConfigResult } from "../../api/generated/settings";
import { importSettings, type EntriesSnapshot, type SettingsScope } from "../../api/hooks/settings";
import { newKey } from "../../api/idempotency";
import { useAuth } from "../../app/providers/AuthProvider";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";
import { Spinner } from "../../components/primitives/Spinner";
import { ConflictView } from "../../components/schema-form/ConflictView";
import { compareRow, sameRowState, sameRowVersion, settingsDocument, type ConflictRow, type RowState } from "../../components/schema-form/draft";
import { PreviewDialog, type PreviewPolicy } from "../../components/schema-form/PreviewDialog";
import { isRecord } from "../../components/schema-form/values";

const maxBytes = 1_048_576;

type Attempt = { id: string; request: ImportConfig; base: EntriesSnapshot; generation: number };

export function ImportDialog({ scope, snapshot, generation, blocked, policy, onClose, onApplied, reload }: {
  scope: SettingsScope;
  snapshot: EntriesSnapshot;
  generation: number;
  blocked: boolean;
  policy: PreviewPolicy;
  onClose(): void;
  onApplied(): void;
  reload(): Promise<EntriesSnapshot | undefined>;
}) {
  const [format, setFormat] = useState<ImportConfig["format"]>("toml");
  const [mode, setMode] = useState<NonNullable<ImportConfig["mode"]>>("merge");
  const [source, setSource] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState<Attempt>();

  if (attempt) return <PreviewDialog key={attempt.id}
    request={attempt.request} policy={policy} simulateConfirmation blocked={blocked}
    stale={attempt.base !== snapshot || attempt.generation !== generation}
    casChanged={attempt.base.digest !== snapshot.digest}
    onClose={() => setAttempt(undefined)}
    renderConflict={(result, pending, retry) => <ImportConflict
      attempt={attempt} result={result} snapshot={snapshot} blocked={blocked || pending} reload={reload} policy={policy}
      onClose={() => { if (!pending) onClose(); }} retry={retry}
      onRebase={(request, base) => setAttempt({ id: newKey(), request, base, generation })} />}
    onApplied={onApplied}
  />;

  function prepare() {
    if (blocked) return;
    if (new TextEncoder().encode(source).length > maxBytes) {
      setError("Документ превышает 1 МиБ.");
      return;
    }
    let document: unknown = source;
    if (format === "json") {
      try {
        document = JSON.parse(source) as unknown;
        if (!isRecord(document)) throw new Error("Expected an object");
      } catch {
        setError("Ожидается документ JSON в виде объекта.");
        return;
      }
    }
    if (typeof document !== "string" && !isRecord(document)) return;
    setError("");
    setAttempt({
      id: newKey(), base: snapshot, generation,
      request: { scope, mode, format, document, expected_entries_digest: snapshot.digest },
    });
  }

  return (
    <Dialog open title="Импорт настроек" onClose={onClose}>
      <form onSubmit={(event) => { event.preventDefault(); prepare(); }}>
        <label>Формат <select value={format} onChange={(event) => setFormat(event.currentTarget.value === "json" ? "json" : "toml")}>
          <option value="toml">TOML</option>
          <option value="json">JSON</option>
        </select></label>{" "}
        <label>Режим <select value={mode} onChange={(event) => setMode(event.currentTarget.value === "replace" ? "replace" : "merge")}>
          <option value="merge">Объединить (merge)</option>
          <option value="replace">Заменить (replace)</option>
        </select></label>
        {mode === "replace" && <p>Записи области, отсутствующие в документе, будут удалены.</p>}
        <p><label>Файл <input type="file" accept=".toml,.json" onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (!file) return;
          if (file.size > maxBytes) {
            setError("Документ превышает 1 МиБ.");
            return;
          }
          void file.text().then((text) => {
            setSource(text);
            setFormat(file.name.toLowerCase().endsWith(".json") ? "json" : "toml");
            setError("");
          }, () => setError("Не удалось прочитать файл."));
        }} /></label></p>
        <label>Документ <textarea rows={10} value={source} onChange={(event) => setSource(event.currentTarget.value)} /></label>
        {error && <p role="alert">{error}</p>}
        <Button type="submit" disabled={blocked || !source.trim()}>Предпросмотр</Button>
      </form>
    </Dialog>
  );
}

function ImportConflict({ attempt, result, snapshot, blocked, reload, policy, onClose, onRebase, retry }: {
  attempt: Attempt;
  result: ImportConfigResult | undefined;
  snapshot: EntriesSnapshot;
  blocked: boolean;
  reload(): Promise<EntriesSnapshot | undefined>;
  policy: PreviewPolicy;
  onClose(): void;
  onRebase(request: ImportConfig, base: EntriesSnapshot): void;
  retry: (() => void) | undefined;
}) {
  const { transport } = useAuth();
  const [beforeReload] = useState(snapshot);
  const [error, setError] = useState("");
  const conflict = useQuery({
    queryKey: ["settings-import-conflict", attempt.id],
    queryFn: async ({ signal }) => {
      const latest = await reload();
      if (!latest) throw new Error("Не удалось получить текущие записи.");
      // The first dry run can lose CAS before returning any parsed entries.
      const proposal = result ?? await importSettings(transport, {
        ...attempt.request, expected_entries_digest: latest.digest, dry_run: true, confirmed: true,
      }, { signal });
      return { latest, proposal };
    },
    retry: false, staleTime: Infinity, gcTime: 0,
  });

  if (!conflict.data) return <Dialog open title="Конфликт изменений" onClose={onClose}>
    {conflict.isError ? <ErrorPanel error={conflict.error} onRetry={() => void conflict.refetch()} /> :
      <Spinner label="Загрузка текущих записей…" />}
  </Dialog>;

  const current = snapshot === beforeReload ? conflict.data.latest : snapshot;
  const baseRows = new Map(attempt.base.entries.map((row) => [row.key, row]));
  const currentRows = new Map(current.entries.map((row) => [row.key, row]));
  const proposal = new Map<string, RowState | null>();
  // Replace proposes removals from the original base. Keep rows created concurrently outside the document.
  if (attempt.request.mode === "replace") {
    for (const key of baseRows.keys()) proposal.set(key, null);
  }
  for (const { key, after, change } of conflict.data.proposal.changes) {
    if (change === "removed" && baseRows.has(key)) proposal.set(key, null);
    if (isRecord(after) && (after.op === "set" || after.op === "append" || after.op === "unset")) {
      proposal.set(key, { op: after.op, value: after.value, locked: after.locked === true });
    }
  }

  const rows = [...new Set([...baseRows.keys(), ...currentRows.keys(), ...proposal.keys()])].flatMap((key): ConflictRow[] => {
    const base = baseRows.get(key) ?? null;
    const now = currentRows.get(key) ?? null;
    const yours = proposal.get(key) ?? null;
    if (proposal.has(key) && !sameRowState(base, yours)) return [compareRow(key, base, now, yours)];
    if (!sameRowVersion(base, now)) return [{ key, base, current: now, yours: base, status: "theirs" as const }];
    return [];
  });

  return <ConflictView key={JSON.stringify([current.digest, current.entries.map(({ entry_id, row_version }) => [entry_id, row_version])])}
    rows={rows} safeValue={policy.safeValue} disabled={blocked || conflict.isFetching} error={error}
    actions={retry && <Button disabled={conflict.isFetching} onClick={retry}>Повторить исходный запрос</Button>}
    onClose={onClose} onRebase={(takeCurrent) => {
      const changes = rows.filter(({ key, current, yours, status }) =>
        status !== "theirs" && !takeCurrent.has(key) && !sameRowState(current, yours));
      const replace = changes.some(({ yours }) => yours === null);
      if (replace && current.hasUnexported) {
        setError("В области есть записи вне каталога. Невозможно сохранить их в документе замены.");
        return;
      }
      const rebased = new Map<string, RowState | null>(replace ? currentRows : []);
      for (const { key, yours } of changes) rebased.set(key, yours);
      onRebase({
        scope: attempt.request.scope, document: settingsDocument(rebased), format: "json",
        mode: replace ? "replace" : "merge", expected_entries_digest: current.digest,
      }, current);
    }} />;
}
