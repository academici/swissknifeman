import { useId, useState } from "react";
import { useParams } from "react-router";
import type { RunsView } from "../../api/generated/execution_10";
import type { PlansView, RevisionsView } from "../../api/generated/planning";
import { field, runLink, runPath } from "../../api/hooks/execution";
import { allowed, segment, useCursor, useRead, withParams } from "../../api/hooks/workspace";
import { keys } from "../../api/keys";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { useStream } from "../../app/providers/StreamProvider";
import { SafeLink } from "../../components/content/SafeLink";
import { Pagination } from "../../components/data/Pagination";
import { Table } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";
import StartRunDialog from "./StartRunDialog";

function RunLauncher({ projectId }: { projectId: string }) {
  const { scope } = useScope();
  const { me } = useAuth();
  const scoped = keys.forScope(scope);
  const [planId, setPlanId] = useState("");
  const [revisionId, setRevisionId] = useState("");
  const [open, setOpen] = useState(false);
  const id = useId();
  const plansPage = useCursor(`/projects/${segment(projectId)}/plans?state=active&purpose=standard`);
  const plans = useRead<PlansView>(scoped.plans(projectId), plansPage.path);
  const plan = plans.data?.items?.find(item => item.plan_id === planId);
  const [before, setBefore] = useState<string[]>([]);
  const revisions = useRead<RevisionsView>(scoped.revisions(planId), withParams(`/plans/${segment(planId)}/revisions`, {
    before: before.at(-1), limit: "50",
  }), Boolean(planId));
  const mayStart = allowed(me, "run.start", planId, projectId, scope.workspaceId);

  return <>
    <label htmlFor={id + "-plan"}>План для запуска</label>
    <select id={id + "-plan"} value={plan?.plan_id ?? ""} onChange={event => {
      setPlanId(event.target.value);
      setRevisionId("");
      setBefore([]);
    }}>
      <option value="">Выберите план</option>
      {plans.data?.items?.map(item => <option key={item.plan_id} value={item.plan_id}>{escapeText(item.alias + " · " + item.title)}</option>)}
    </select>
    {plans.isError && <ErrorPanel error={plans.error} />}
    {plans.data && <Pagination {...plansPage} next={plans.data.next_cursor} />}
    {plan && <>
      <label htmlFor={id + "-revision"}>Опубликованная ревизия</label>
      <select id={id + "-revision"} value={revisionId} onChange={event => setRevisionId(event.target.value)}>
        <option value="">Выберите ревизию</option>
        {revisions.data?.items.map(item => <option key={item.revision_id} value={item.revision_id}>r{item.revision_no}</option>)}
      </select>
      {revisions.isError && <ErrorPanel error={revisions.error} />}
      {revisions.data && <Pagination
        next={revisions.data.next_cursor}
        onNext={cursor => { setBefore([...before, cursor]); setRevisionId(""); }}
        {...(before.length ? { onPrevious: () => { setBefore(before.slice(0, -1)); setRevisionId(""); } } : {})}
      />}
      {mayStart && <Button disabled={!revisionId} onClick={() => setOpen(true)}>Новый запуск</Button>}
      <StartRunDialog open={open && mayStart} planId={planId} revisionId={revisionId} projectId={projectId}
        onClose={() => setOpen(false)} />
    </>}
  </>;
}

export default function RunsPage() {
  const { projectId = "" } = useParams();
  const { scope } = useScope();
  const { me } = useAuth();
  const { stale } = useStream();
  const cursor = useCursor(`/projects/${segment(projectId)}/runs?kinds=plan,review_request,readiness_audit`);
  const runs = useRead<RunsView>(keys.forScope(scope).runs(projectId), cursor.path, Boolean(projectId));
  const hasStartGrant = allowed(me, "run.start", projectId, scope.workspaceId)
    || Object.values(me?.permissions_by_scope ?? {}).some(grants => grants.includes("run.start"));

  return <section>
    <h1>Запуски</h1>
    {stale && <p role="status">Данные могут быть устаревшими.</p>}
    {hasStartGrant && <RunLauncher key={projectId} projectId={projectId} />}
    {runs.isError ? <ErrorPanel error={runs.error} onRetry={() => { void runs.refetch(); }} />
      : runs.data ? <>
        <Table rows={runs.data.items} rowKey={run => field(run.run_id)} empty="Нет запусков" columns={[
          { id: "run", header: "Запуск", cell: run => <SafeLink href={runLink(runPath(field(run.run_id)), projectId)}>
            {`${field(run.plan_alias, field(run.run_id))} · r${field(run.revision_no)}`}
          </SafeLink> },
          { id: "kind", header: "Тип", cell: run => escapeText(field(run.kind)) },
          { id: "status", header: "Статус", cell: run => <StatusBadge status={field(run.status)} /> },
          { id: "progress", header: "Принятые задачи", cell: run => escapeText(`${field(run.tasks_accepted)} / ${field(run.tasks_total)}`) },
          { id: "started", header: "Начало", cell: run => escapeText(field(run.started_at, "—")) },
        ]} />
        <Pagination {...cursor} next={runs.data.next_after} busy={runs.isFetching} />
      </> : <Skeleton />}
  </section>;
}
