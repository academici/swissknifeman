import { lazy, Suspense, useState } from "react";
import { useAuth } from "../../app/providers/AuthProvider";
import { useNavigate, useParams } from "react-router";
import type { PlanView } from "../../api/generated/planning";
import {
  planPath, useArchivePlan, useDrafts, useExport, useOpenDraft, usePlan, usePlanPermissions, useRevisions,
} from "../../api/hooks/planning";
import { SafeLink } from "../../components/content/SafeLink";
import { EmptyState } from "../../components/data/EmptyState";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { ConfirmDialog } from "../../components/primitives/ConfirmDialog";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { Tabs } from "../../components/primitives/Tabs";
import { escapeText } from "../../lib/safeText";
import StartRunDialog from "../runs/StartRunDialog";
import { PlanTree } from "./PlanTree";
import { ReadyPreviewTab } from "./ReadyPreviewTab";
import { PlanCommandError, RevisionsTab } from "./RevisionsTab";

const PlanVisaPanel = lazy(() => import("./PlanVisaPanel"));
const SimulatePanel = lazy(() => import("./SimulatePanel"));

function DraftsTab({ planId }: { planId: string }) {
  const drafts = useDrafts(planId);
  if (drafts.error) return <ErrorPanel error={drafts.error} onRetry={() => void drafts.refetch()} />;
  if (!drafts.data) return <Skeleton />;
  return <Table rows={drafts.data.items} rowKey={(d) => d.draft_id} empty="Нет открытых черновиков" columns={[
    { id: "draft", header: "Черновик", cell: (d) => <SafeLink href={planPath(planId) + "/drafts/" + encodeURIComponent(d.draft_id)}>{d.draft_id}</SafeLink> },
    { id: "version", header: "Версия правок", cell: (d) => d.edit_version },
    { id: "base", header: "Базовая ревизия", cell: (d) => d.base_revision_no ?? "—" },
    { id: "stale", header: "База устарела", cell: (d) => d.stale ? "Да" : "Нет" },
  ]} />;
}

function RevisionExport({ planId, revisionId }: { planId: string; revisionId: string }) {
  const spec = useExport(planId, { revisionId }, false);
  async function download() {
    const result = await spec.refetch();
    if (result.isError || !result.data) return;
    const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    try {
      link.href = url;
      link.download = `plan-${revisionId}.json`;
      link.click();
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 0);
    }
  }
  return <><Button disabled={spec.isFetching} onClick={() => void download()}>Экспорт</Button>
    {spec.error && <ErrorPanel error={spec.error} />}</>;
}

function StartRevisionRun({ plan, revisionId }: { plan: PlanView; revisionId: string }) {
  const [open, setOpen] = useState(false);
  return <>
    <Button onClick={() => setOpen(true)}>Запустить</Button>
    <StartRunDialog open={open} onClose={() => setOpen(false)} planId={plan.plan_id}
      revisionId={revisionId} projectId={plan.project_id} />
  </>;
}

function PlanDetails({ plan, revisionId, reload }: { plan: PlanView; revisionId: string | null; reload(): void }) {
  const navigate = useNavigate();
  const { me } = useAuth();
  const [tab, setTab] = useState("tree");
  const [archiveVersion, setArchiveVersion] = useState<number | null>(null);
  const revisions = useRevisions(plan.plan_id);
  const permissions = usePlanPermissions("plan", plan.plan_id);
  const archive = useArchivePlan(plan.plan_id);
  const open = useOpenDraft();
  const canWrite = plan.lifecycle_state === "active" && !archive.isPending;
  const canArchive = canWrite && permissions.has("plan.archive");
  const empty = <EmptyState title="Нет опубликованных ревизий" />;
  return <>
    <h2>{escapeText(plan.alias)} · {escapeText(plan.title)}</h2>
    <StatusBadge status={plan.lifecycle_state} />
    {revisionId && <label>Ревизия <select value={revisionId} onChange={(e) =>
      void navigate(planPath(plan.plan_id) + "/revisions/" + encodeURIComponent(e.target.value))}>
      {!revisions.data?.items.some((r) => r.revision_id === revisionId) &&
        <option value={revisionId}>{revisionId === plan.current_revision_id ? `r${plan.current_revision_no}` : escapeText(revisionId)}</option>}
      {revisions.data?.items.map((r) => <option key={r.revision_id} value={r.revision_id}>r{r.revision_no}{r.revision_id === plan.current_revision_id ? " · текущая" : ""}</option>)}
    </select></label>}
    {revisions.error && <ErrorPanel error={revisions.error} onRetry={() => void revisions.refetch()} />}
    <Button disabled={!canWrite || !permissions.has("plan.edit") || open.isPending} onClick={() => {
      open.mutate({ plan_id: plan.plan_id, base: plan.current_revision_id ? "current" : "empty" }, {
        onSuccess: (d) => { void navigate(planPath(plan.plan_id) + "/drafts/" + encodeURIComponent(d.draft_id)); },
      });
    }}>Открыть черновик</Button>
    <Button disabled={!canArchive} onClick={() => setArchiveVersion(plan.row_version)}>Архивировать</Button>
    {revisionId && <RevisionExport key={revisionId} planId={plan.plan_id} revisionId={revisionId} />}
    {revisionId && plan.lifecycle_state === "active" && permissions.has("run.start") &&
      <StartRevisionRun key={`start:${revisionId}`} plan={plan} revisionId={revisionId} />}
    {open.error && <PlanCommandError error={open.error} submitted={open.variables} reload={() => { open.reset(); reload(); }} />}
    {archive.error && <PlanCommandError error={archive.error} submitted={{ row_version: archive.variables }}
      reload={() => { archive.reset(); reload(); }} />}
    {archiveVersion !== null && <ConfirmDialog open destructive requireReason title="Архивировать план?"
      description="Все открытые черновики будут закрыты." confirmLabel="Архивировать" onClose={() => setArchiveVersion(null)}
      onConfirm={() => { if (canArchive) archive.mutate(archiveVersion); setArchiveVersion(null); }} />}
    <Tabs label="План" active={tab} onSelect={setTab} tabs={[
      { id: "tree", label: "Дерево", content: revisionId ? <PlanTree key={revisionId} planId={plan.plan_id} revisionId={revisionId} /> : empty },
      { id: "revisions", label: "Ревизии", content: <RevisionsTab plan={plan} canRestore={canWrite && permissions.has("plan.publish")} reload={reload} /> },
      { id: "preview", label: "Предпросмотр", content: revisionId ? <ReadyPreviewTab key={revisionId} planId={plan.plan_id} source={{ revisionId }} /> : empty },
      { id: "simulate", label: "Симуляция", content: revisionId ?
        <Suspense fallback={<Skeleton />}><SimulatePanel key={revisionId} planId={plan.plan_id} source={{ revisionId }} /></Suspense> : empty },
      { id: "visa", label: "PlanVisa", content: revisionId ?
        <Suspense fallback={<Skeleton />}><PlanVisaPanel key={revisionId} planId={plan.plan_id} revisionId={revisionId}
          canApprove={canWrite && me?.principal.kind === "human" && permissions.has("plan.approve")}
          canValidate={canWrite && permissions.has("run.start")} /></Suspense> : empty },
      { id: "drafts", label: `Черновики (${plan.open_drafts})`, content: <DraftsTab planId={plan.plan_id} /> },
    ]} />
  </>;
}

export default function PlanPage() {
  const { planId = "", revisionId } = useParams();
  const plan = usePlan(planId);
  return <section><h1>План</h1>
    {plan.error ? <ErrorPanel error={plan.error} onRetry={() => void plan.refetch()} /> : plan.data
      ? <PlanDetails key={planId} plan={plan.data} revisionId={revisionId ?? plan.data.current_revision_id} reload={() => void plan.refetch()} />
      : <Skeleton />}
  </section>;
}
