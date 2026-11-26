import { useState } from "react";
import { ApiError } from "../../api/errors";
import type { PublicationPreviewView } from "../../api/generated/planning";
import { planPath, usePublicationPreview, usePublishDraft } from "../../api/hooks/planning";
import { newKey } from "../../api/idempotency";
import { SafeLink } from "../../components/content/SafeLink";
import { KeyValue } from "../../components/data/KeyValue";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";
import { Skeleton } from "../../components/primitives/Skeleton";
import { DiffView, type DiffKind } from "../../components/viz/DiffView";
import { escapeText } from "../../lib/safeText";
import { FindingsPanel, problemFindings } from "./FindingsPanel";

function fieldChange(field: PublicationPreviewView["diff"]["plan_fields"][number]) {
  return {
    id: field.pointer, kind: { add: "added", remove: "removed", replace: "changed" }[field.op] as DiffKind,
    label: field.pointer, before: JSON.stringify(field.before), after: JSON.stringify(field.after),
  };
}

function PreparedContent({ preview }: { preview: PublicationPreviewView }) {
  const changes = preview.diff.entities.flatMap((entity) => {
    const kinds: DiffKind[] = [entity.change];
    if (entity.rekeyed) kinds.push("rekeyed");
    if (entity.moved) kinds.push("moved");
    return kinds.map((kind) => ({
      id: entity.entity_id, kind,
      label: [entity.entity_kind, entity.key_after ?? entity.key_before, ...(
        kind === entity.change ? entity.fields.map((field) =>
          `${field.pointer} · ${JSON.stringify(field.before)} → ${JSON.stringify(field.after)}`) : []
      )].filter(Boolean).join(" · "),
      ...(entity.key_before === null ? {} : { before: entity.key_before }),
      ...(entity.key_after === null ? {} : { after: entity.key_after }),
    }));
  });
  return <>
    <dl>
      <KeyValue label="Сохранённая версия" value={preview.source.kind === "draft" ? `v${preview.source.edit_version}` : "—"} />
      <KeyValue label="Базовая ревизия" value={preview.base_revision_id ?? "—"} />
      <KeyValue label="Digest подготовленного содержания" value={preview.content_digest} />
    </dl>
    {preview.no_changes ? <p>Изменений для публикации нет.</p> : <section>
      <h3>Подготовленные изменения</h3>
      <DiffView changes={[...preview.diff.plan_fields.map(fieldChange), ...changes]} />
    </section>}
    <section>
      <h3>Зафиксированные версии материалов</h3>
      {preview.pinned_materials.length ? <ul>{preview.pinned_materials.map((pin) => <li key={pin.material_key}>
        {escapeText(pin.material_key)} · <code>{escapeText(pin.file_version_id)}</code> · {escapeText(pin.resolved_from)}
      </li>)}</ul> : <p>Нет материалов</p>}
    </section>
    <FindingsPanel report={preview.validation} />
    {!preview.publishable && !preview.no_changes && <p role="status">Черновик пока нельзя опубликовать.</p>}
  </>;
}

interface PublishProps {
  planId: string;
  draftId: string;
  version: number;
  epoch: number;
  canPreview: boolean;
  canReplay: boolean;
  onClose(): void;
  onRebase?: () => void;
}

export function PublishDialog(props: PublishProps) {
  const { canPreview, epoch, version } = props;
  const [attempt, setAttempt] = useState(() => ({ key: newKey(), version, epoch }));
  const [reason, setReason] = useState("");
  return <PublishAttempt key={attempt.key} {...props} attempt={attempt} reason={reason} setReason={setReason}
    refresh={() => { if (canPreview) setAttempt({ key: newKey(), version, epoch }); }} />;
}

function PublishAttempt({ planId, draftId, version, epoch, canPreview, canReplay, onClose, onRebase, attempt, reason, setReason, refresh }:
  PublishProps & {
    attempt: { key: string; version: number; epoch: number };
    reason: string;
    setReason(reason: string): void;
    refresh(): void;
  }) {
  const { preview, invalidated } = usePublicationPreview(planId, draftId, attempt.version, attempt.key);
  const publish = usePublishDraft(planId, draftId);
  const error = publish.error ?? preview.error;
  const problem = error instanceof ApiError ? error : undefined;
  const changed = problem?.code === "VERSION_CONFLICT" && problem.details.reason === "candidate_changed";
  const baseChanged = problem?.code === "BASE_REVISION_CHANGED";
  const notReady = problem?.code === "PLAN_NOT_READY" || problem?.code === "NO_CHANGES";
  const stale = invalidated || version !== attempt.version || epoch !== attempt.epoch ||
    problem?.code === "VERSION_CONFLICT" || baseChanged || notReady;
  const retrying = publish.status === "error" && problem?.retryable === true && !changed && !baseChanged;
  const pending = publish.status === "pending";
  const data = preview.data;
  const source = data?.source.kind === "draft" ? data.source : undefined;
  const matches = source?.edit_version === attempt.version && source.draft_id === draftId && source.plan_id === planId;
  const reasonText = reason.trim();
  const reasonLength = Array.from(reasonText).length;
  const canPublish = canPreview && !stale && !pending && !retrying && matches && data?.publishable && !data.no_changes
    && reasonLength > 0 && reasonLength <= 2000;

  return <Dialog open title="Публикация черновика" onClose={() => { if (!pending) onClose(); }}>
    {publish.data ? <p role="status">
      Опубликована <SafeLink href={planPath(planId) + "/revisions/" + encodeURIComponent(publish.data.revision_id)}>
        ревизия r{publish.data.revision_no}
      </SafeLink>
    </p> : <>
      {preview.isPending && <Skeleton />}
      {data && <PreparedContent preview={data} />}
      {changed ? <p role="alert">Prepared content changed</p>
        : stale && <p role="status">Предпросмотр устарел.</p>}
      {problem?.code === "PLAN_NOT_READY" ? <FindingsPanel report={problemFindings(problem.details)} />
        : error && !changed && <ErrorPanel error={error} />}
      {baseChanged && onRebase && <Button disabled={pending} onClick={onRebase}>Rebase</Button>}
      {(stale || preview.isError) && <Button disabled={!canPreview || pending} onClick={refresh}>Refresh preview</Button>}
      <form onSubmit={(event) => {
        event.preventDefault();
        if (canPublish && source && data) publish.submit({
          expected_edit_version: source.edit_version, expected_content_digest: data.content_digest, reason: reasonText,
        });
      }}>
        <label>Причина публикации <textarea value={reason} required maxLength={4000} disabled={pending || retrying}
          onChange={(event) => setReason(event.target.value)} /></label>
        {reasonLength > 2000 && <p role="alert">Причина должна содержать до 2000 символов.</p>}
        <Button type="submit" disabled={!canPublish}>Publish shown changes</Button>
        {retrying && <Button disabled={!canReplay || version !== attempt.version || epoch !== attempt.epoch}
          onClick={publish.retry}>Повторить публикацию</Button>}
      </form>
    </>}
  </Dialog>;
}
