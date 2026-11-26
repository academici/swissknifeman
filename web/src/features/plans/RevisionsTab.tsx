import { useState } from "react";
import { ApiError } from "../../api/errors";
import type { PlanView } from "../../api/generated/planning";
import { planPath, useRestoreRevision, useRevisions } from "../../api/hooks/planning";
import { SafeLink } from "../../components/content/SafeLink";
import { Pagination } from "../../components/data/Pagination";
import { RelativeTime } from "../../components/data/RelativeTime";
import { Table } from "../../components/data/Table";
import { ConflictPanel } from "../../components/feedback/ConflictPanel";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { Skeleton } from "../../components/primitives/Skeleton";
import { escapeText } from "../../lib/safeText";

export function PlanCommandError({ error, submitted, reload }: { error: unknown; submitted: unknown; reload(): void }) {
  return error instanceof ApiError && error.isConflict()
    ? <ConflictPanel error={error} submitted={submitted} current={error.details} onReload={reload} />
    : <ErrorPanel error={error} />;
}

export function RevisionsTab({ plan, canRestore, reload }: { plan: PlanView; canRestore: boolean; reload(): void }) {
  const [pages, setPages] = useState<string[]>([]);
  const revisions = useRevisions(plan.plan_id, pages.at(-1));
  const restore = useRestoreRevision(plan.plan_id);
  const [target, setTarget] = useState<{ no: number; head: NonNullable<PlanView["current_revision_id"]> } | null>(null);
  const allowed = canRestore && plan.lifecycle_state === "active";
  const url = (id: string) => planPath(plan.plan_id) + "/revisions/" + encodeURIComponent(id);
  return <section>
    {restore.data && <p role="status">Создана ревизия <SafeLink href={url(restore.data.revision_id)}>r{restore.data.revision_no}</SafeLink></p>}
    {restore.error && <PlanCommandError error={restore.error} submitted={restore.variables}
      reload={() => { restore.reset(); reload(); void revisions.refetch(); }} />}
    {revisions.error ? <ErrorPanel error={revisions.error} onRetry={() => void revisions.refetch()} /> : !revisions.data ? <Skeleton /> : <>
      <Table rows={revisions.data.items} rowKey={(r) => r.revision_id} empty="Нет ревизий" columns={[
        { id: "revision", header: "Ревизия", cell: (r) => <SafeLink href={url(r.revision_id)}>r{r.revision_no}</SafeLink> },
        { id: "origin", header: "Источник", cell: (r) => escapeText(r.origin) },
        { id: "restored", header: "Восстановлена из", cell: (r) => r.restored_from_revision_no ?? "—" },
        { id: "reason", header: "Причина", cell: (r) => escapeText(r.change_reason) },
        { id: "time", header: "Опубликована", cell: (r) => <RelativeTime value={r.published_at} /> },
        { id: "digest", header: "Digest", cell: (r) => <code>{escapeText(r.content_digest)}</code> },
        { id: "actions", header: "Действия", cell: (r) => <>
          {r.parent_revision_id && <SafeLink href={url(r.revision_id) + "/diff/" + encodeURIComponent(r.parent_revision_id)}>Сравнить с родительской</SafeLink>}
          <Button disabled={!allowed || !plan.current_revision_id || restore.isPending}
            onClick={() => plan.current_revision_id && setTarget({ no: r.revision_no, head: plan.current_revision_id })}>Восстановить</Button>
        </> },
      ]} />
      <Pagination next={revisions.data.next_cursor} onNext={(cursor) => setPages([...pages, cursor])}
        {...(pages.length ? { onPrevious: () => setPages(pages.slice(0, -1)) } : {})} />
    </>}
    {target && <ConfirmDialog open title={`Восстановить ревизию r${target.no}?`} onClose={() => setTarget(null)}
      confirmLabel="Восстановить" onConfirm={(reason) => {
        if (!allowed || !reason || reason.length > 2000 || restore.isPending) return;
        restore.mutate({ revision_no: target.no, reason, expected_current_revision_id: target.head });
        setTarget(null);
      }}>
      <label>Причина <textarea name="reason" required maxLength={2000} /></label>
    </ConfirmDialog>}
  </section>;
}
