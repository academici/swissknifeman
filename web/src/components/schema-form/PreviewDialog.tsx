import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { ApiError } from "../../api/errors";
import type { ImportConfig, ImportConfigResult } from "../../api/generated/settings";
import { importSettings, isSettingsConflict, scopeName } from "../../api/hooks/settings";
import { newKey, useIdempotentMutation } from "../../api/idempotency";
import { useAuth } from "../../app/providers/AuthProvider";
import { escapeText } from "../../lib/safeText";
import { Table } from "../data/Table";
import { ErrorPanel } from "../feedback/ErrorPanel";
import { Button } from "../primitives/Button";
import { Dialog } from "../primitives/Dialog";
import { Spinner } from "../primitives/Spinner";
import { SettingValue } from "./ProvenanceBadge";
import { isRecord, own } from "./values";

type Change = ImportConfigResult["changes"][number];
type Effective = ImportConfigResult["effective_diff"][number];
type Problem = ImportConfigResult["problems"][number];

export interface PreviewPolicy {
  mayChange(change: Change): boolean;
  needsConfirmation(key: string): boolean;
  safeValue(key: string, value: unknown): unknown;
  problemMessage(problem: Problem): string;
}

export function PreviewDialog({
  request, policy, simulateConfirmation, stale, blocked, casChanged,
  onClose, onConflict, renderConflict, onApplied, onSubmit,
}: {
  request: ImportConfig;
  policy: PreviewPolicy;
  simulateConfirmation: boolean;
  stale: boolean;
  blocked: boolean;
  casChanged: boolean;
  onClose(): void;
  onConflict?(): void;
  renderConflict?(result: ImportConfigResult | undefined, pending: boolean, retry: (() => void) | undefined): ReactNode;
  onApplied(): void;
  onSubmit?(): void;
}) {
  const { transport } = useAuth();
  const [previewId] = useState(newKey);
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const preview = useQuery({
    queryKey: ["settings-preview", previewId],
    queryFn: ({ signal }) => importSettings(transport, {
      ...request, dry_run: true, confirmed: simulateConfirmation,
    }, { signal }),
    retry: false, staleTime: Infinity, gcTime: 0,
  });
  const apply = useIdempotentMutation(async (body: ImportConfig, idempotencyKey) => {
    try {
      const result = await importSettings(transport, body, { idempotencyKey });
      if (!result.applied) throw new Error("Settings were not applied");
      onApplied();
      return result;
    } catch (error) {
      if (isSettingsConflict(error)) onConflict?.();
      throw error;
    }
  });
  const previewConflict = isSettingsConflict(preview.error);
  const changes = preview.data?.changes.filter(({ change }) => change !== "unchanged") ?? [];
  const unauthorized = changes.some((change) => !policy.mayChange(change));
  const requiresConfirmation = changes.some(({ key }) => policy.needsConfirmation(key));
  const drift = stale || previewConflict || isSettingsConflict(apply.error);
  const busy = apply.status === "pending";
  const retryable = apply.error instanceof ApiError && (apply.error.status === 0 || apply.error.status >= 500);
  // A stale request may be retried with its original body when the observed digest fails its CAS.
  const canRetry = retryable && !blocked && !unauthorized && (!drift || casChanged);
  const ready = changes.length > 0 && !blocked && !drift && !unauthorized && preview.data?.problems.length === 0 &&
    (!requiresConfirmation || confirmed) && apply.status === "idle";
  useEffect(() => {
    if (previewConflict) onConflict?.();
  }, [previewConflict, onConflict]);
  if (renderConflict && drift && !preview.isPending) {
    return renderConflict(preview.data, busy, canRetry ? apply.retry : undefined);
  }
  const state = (key: string, row: unknown) => isRecord(row) ? <>
    {typeof row.op === "string" && escapeText(row.op)}{row.locked === true && " · 🔒"}{" "}
    <SettingValue value={policy.safeValue(key, own(row, "value"))} />
  </> : <SettingValue value={policy.safeValue(key, row)} />;

  return (
    <Dialog open title={`Предпросмотр · ${scopeName(request.scope)}`} onClose={() => { if (!busy) onClose(); }}>
      {preview.isPending && <Spinner label="Подготовка предпросмотра…" />}
      {drift && <p role="alert">Предпросмотр устарел. Обновите данные перед применением.</p>}
      {preview.isError && <ErrorPanel error={preview.error} />}
      {apply.error && <ErrorPanel error={apply.error} />}
      {preview.data && <>
        <h3>Изменения записей</h3>
        <Table<Change> rows={changes} rowKey={(row) => row.key} empty="Нет изменений" columns={[
          { id: "key", header: "Ключ", cell: ({ key }) => <code>{escapeText(key)}</code> },
          { id: "change", header: "Операция", cell: ({ change }) => escapeText(change) },
          { id: "before", header: "До", cell: ({ key, before }) => state(key, before) },
          { id: "after", header: "После", cell: ({ key, after }) => state(key, after) },
        ]} />
        <h3>Эффективные значения</h3>
        <Table<Effective> rows={preview.data.effective_diff} rowKey={(row) => row.key}
          empty="Эффективные значения не изменятся" columns={[
            { id: "key", header: "Ключ", cell: ({ key }) => <code>{escapeText(key)}</code> },
            { id: "before", header: "До", cell: ({ key, before }) => <SettingValue value={policy.safeValue(key, before)} /> },
            { id: "after", header: "После", cell: ({ key, after }) => <SettingValue value={policy.safeValue(key, after)} /> },
          ]} />
        {preview.data.problems.length > 0 && <ul aria-label="Ошибки предпросмотра" role="alert">
          {preview.data.problems.map((problem, index) => (
            <li key={index}>
              {[problem.key, problem.pointer, problem.code, policy.problemMessage(problem)]
                .filter(Boolean).map((text) => escapeText(text ?? "")).join(" · ")}
            </li>
          ))}
        </ul>}
        {unauthorized && <p role="alert">Одно или несколько изменений недоступны в этой области.</p>}
        <label>Причина <input value={reason} maxLength={2000} disabled={apply.status !== "idle"}
          onChange={(event) => setReason(event.currentTarget.value)} /></label>
        {requiresConfirmation && <label>
          <input type="checkbox" checked={confirmed} disabled={apply.status !== "idle"}
            onChange={(event) => setConfirmed(event.currentTarget.checked)} />
          Подтверждаю изменение параметров, требующих подтверждения
        </label>}
        <Button disabled={!ready} onClick={() => {
          if (!ready || !preview.data) return;
          onSubmit?.();
          apply.submit({
            ...request, dry_run: false, expected_entries_digest: preview.data.entries_digest_before,
            reason: reason.trim(), confirmed: requiresConfirmation && confirmed,
          });
        }}>Применить</Button>
        {retryable && <Button disabled={!canRetry} onClick={() => { if (canRetry) apply.retry(); }}>Повторить применение</Button>}
      </>}
    </Dialog>
  );
}
