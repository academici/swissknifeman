import { useState, type FormEvent } from "react";
import type { ReadyPreviewViewDefsRoute } from "../../api/generated/planning";
import { useReadyPreview, type PlanSource, type PreviewOptions } from "../../api/hooks/planning";
import { EmptyState } from "../../components/data/EmptyState";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { escapeText } from "../../lib/safeText";

function routeLabel(route: ReadyPreviewViewDefsRoute) {
  const correction = route.correction && `correction ${route.correction.class} / ${route.correction.effort}`;
  return [route.class, route.effort, route.runtime, route.model, correction].filter(Boolean).join(" / ");
}

export function ReadyPreviewTab({ planId, source }: { planId: string; source: PlanSource }) {
  const [options, setOptions] = useState<PreviewOptions>({});
  const preview = useReadyPreview(planId, source, options);
  function apply(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const done = String(form.get("done") ?? "").split(/[,\s]+/u).filter(Boolean);
    const granted = String(form.get("granted") ?? "").split(",").map((label) => label.trim()).filter(Boolean);
    const limit = form.get("limit");
    setOptions({ assume_done: done, assume_granted: granted, ...(limit ? { limit: Number(limit) } : {}) });
  }
  const view = preview.data;
  return <section>
    <form onSubmit={apply}>
      <label>Считать завершёнными <input name="done" placeholder="P1.1, P1.2/U1" /></label>
      <label>Считать разрешёнными <input name="granted" /></label>
      <label>Лимит <input type="number" min={1} max={64} name="limit" placeholder="8" /></label>
      <Button type="submit">Показать предпросмотр</Button>
    </form>
    {preview.error ? <ErrorPanel error={preview.error} onRetry={() => void preview.refetch()} /> : !view ? <Skeleton /> : <>
      <h3>Дорожки · лимит {view.limit}</h3>
      {!view.lanes.length && <EmptyState title="Нет готовых дорожек" />}
      <ol>{view.lanes.map((lane) => <li key={JSON.stringify(lane.tasks)}>
        {escapeText(lane.kind)} · {escapeText(lane.tasks.join(", "))}
        {lane.batch_key && <> · {escapeText(lane.batch_key)}</>}
        {lane.route && <> · {escapeText(routeLabel(lane.route))}</>}
      </li>)}</ol>
      <h3>Ожидают</h3>
      <ul>{view.waiting.map((w) => <li key={w.task}>{escapeText([w.task, w.reason, ...w.detail].join(" · "))}</li>)}</ul>
      <h3>Конфликты</h3>
      <ul>{view.conflicts.map((c) => <li key={JSON.stringify([c.task, c.with_task])}>
        {escapeText([c.task, c.with_task, c.reason, ...c.paths].join(" · "))}</li>)}</ul>
      <h3>Отложены</h3>
      <ul>{view.deferred.map((task) => <li key={task}>{escapeText(task)}</li>)}</ul>
      <h3>Группы маршрутов</h3>
      <ul>{view.route_groups.map((g) => <li key={JSON.stringify(g.lanes)}>
        {escapeText(routeLabel(g.route))} · {g.lanes.map((i) => i + 1).join(", ")}</li>)}</ul>
    </>}
  </section>;
}
