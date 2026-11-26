import { lazy, Suspense, useState } from "react";
import { useParams } from "react-router";
import type { ListPlans, PlanSummaryView } from "../../api/generated/planning";
import { planPath, usePlanPermissions, usePlans } from "../../api/hooks/planning";
import { SafeLink } from "../../components/content/SafeLink";
import { Filters } from "../../components/data/Filters";
import { Pagination } from "../../components/data/Pagination";
import { RelativeTime } from "../../components/data/RelativeTime";
import { Table, type Column } from "../../components/data/Table";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";
const CreatePlanWizard = lazy(() => import("./CreatePlanWizard"));

const columns: Column<PlanSummaryView>[] = [
  { id: "alias", header: "План", cell: (p) => <SafeLink href={planPath(p.plan_id)}>{p.alias}</SafeLink> },
  { id: "title", header: "Название", cell: (p) => escapeText(p.title) },
  { id: "revision", header: "Ревизия", cell: (p) => p.current_revision_no ?? "—" },
  { id: "drafts", header: "Открытые черновики", cell: (p) => p.open_drafts },
  { id: "state", header: "Состояние", cell: (p) => <StatusBadge status={p.lifecycle_state} /> },
  { id: "time", header: "Обновлён", cell: (p) => <RelativeTime value={p.updated_at} /> },
];

function ProjectPlans({ projectId }: { projectId: string }) {
  const [state, setState] = useState<NonNullable<ListPlans["state"]>>("active");
  const [pages, setPages] = useState<string[]>([]);
  const [create, setCreate] = useState(false);
  const plans = usePlans(projectId, state, pages.at(-1));
  const rights = usePlanPermissions("project", projectId);
  function filter(value: typeof state) { setState(value); setPages([]); }
  return <section>
    <h1>Планы</h1>
    {rights.has("plan.create") && <Button onClick={() => setCreate(true)}>Создать план</Button>}
    <Filters onReset={() => filter("active")}>
      <label>Состояние <select value={state} onChange={(e) => filter(e.target.value as typeof state)}>
        <option value="active">Активные</option><option value="archived">Архивные</option><option value="all">Все</option>
      </select></label>
    </Filters>
    {plans.isError ? <ErrorPanel error={plans.error} onRetry={() => void plans.refetch()} /> : plans.data ? <>
      <Table columns={columns} rows={plans.data.items.filter((p) => p.purpose === "standard")} rowKey={(p) => p.plan_id} empty="Планов нет" />
      <Pagination next={plans.data.next_cursor} onNext={(next) => setPages([...pages, next])}
        {...(pages.length ? { onPrevious: () => setPages(pages.slice(0, -1)) } : {})} />
    </> : <Skeleton />}
    {create && <Suspense fallback={<Skeleton />}>
      <CreatePlanWizard projectId={projectId} canDesign={rights.has("plan.edit")}
        canResearch={rights.has("context.research")} onClose={() => setCreate(false)} />
    </Suspense>}
  </section>;
}

export default function PlansPage() {
  const { projectId = "" } = useParams();
  return <ProjectPlans key={projectId} projectId={projectId} />;
}
