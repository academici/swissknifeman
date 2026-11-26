import { useId, useState } from "react";
import { useParams } from "react-router";
import type { ReviewRoiView, RunsView } from "../../api/generated/execution";
import { field } from "../../api/hooks/execution";
import { segment, useCursor, useRead } from "../../api/hooks/workspace";
import { keys } from "../../api/keys";
import { useScope } from "../../app/providers/ScopeProvider";
import { useStream } from "../../app/providers/StreamProvider";
import { Pagination } from "../../components/data/Pagination";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Spinner } from "../../components/primitives/Spinner";
import { escapeText } from "../../lib/safeText";

function ReviewRoi({ runId }: { runId: string }) {
  const { scope } = useScope();
  const report = useRead<ReviewRoiView>(
    keys.forScope(scope).reviewRoi(runId), `/runs/${segment(runId)}/analytics/review-roi`,
  );
  if (report.isError) return <ErrorPanel error={report.error} onRetry={() => { void report.refetch(); }} />;
  if (!report.data) return <Spinner label="Загрузка отчёта…" />;
  const data = report.data;
  const finished = data.finished_reviewer_steps;
  if (finished === 0 && data.completed_agent_reviews === 0 && data.completed_human_reviews === 0) {
    return <p>В этом запуске пока нет завершённых ревью или шагов ревьюера.</p>;
  }

  return <>
    <dl>
      <dt>Завершённые ревью агентов</dt><dd>{data.completed_agent_reviews}</dd>
      <dt>Завершённые ревью людей</dt><dd>{data.completed_human_reviews}</dd>
      <dt>Уникальные замечания</dt><dd>{data.unique_findings}</dd>
      <dt>Устранённые замечания</dt><dd>{data.resolved_findings}</dd>
      <dt>Отклонённые замечания</dt><dd>{data.rejected_findings}</dd>
      <dt>Завершённые шаги ревьюера</dt><dd>{finished}</dd>
      <dt>Зафиксированные затраты, USD</dt><dd>{data.observed_cost_usd ?? "Нет данных"}</dd>
      <dt>Шаги с данными о затратах</dt><dd>{data.priced_reviewer_steps} из {finished}</dd>
      <dt>Зафиксированное время работы, мс</dt><dd>{data.observed_duration_ms ?? "Нет данных"}</dd>
      <dt>Шаги с данными о времени</dt><dd>{data.timed_reviewer_steps} из {finished}</dd>
    </dl>
    <p>Затраты и время учитывают только шаги с измерениями. Для оценки эффекта ревью нужна размеченная выборка для сравнения.</p>
  </>;
}

function RunSelection({ projectId }: { projectId: string }) {
  const { scope } = useScope();
  const [runId, setRunId] = useState("");
  const selectId = useId();
  const cursor = useCursor(`/projects/${segment(projectId)}/runs?kinds=plan,review_request,readiness_audit,adhoc`);
  const runs = useRead<RunsView>(keys.forScope(scope).runs(projectId), cursor.path);
  if (runs.isError) return <ErrorPanel error={runs.error} onRetry={() => { void runs.refetch(); }} />;
  if (!runs.data) return <Spinner label="Загрузка запусков…" />;
  if (runs.data.items.length === 0 && cursor.onPrevious === undefined) return <p>Нет запусков.</p>;
  const selected = runs.data.items.some(run => run.run_id === runId) ? runId : "";

  return <>
    <label htmlFor={selectId}>Запуск</label>
    <select id={selectId} value={selected} onChange={event => setRunId(event.target.value)}>
      <option value="">Выберите запуск</option>
      {runs.data.items.map(run => {
        const id = field(run.run_id);
        return <option key={id} value={id}>{escapeText(`${field(run.plan_alias, field(run.kind))} · ${id}`)}</option>;
      })}
    </select>
    <Pagination next={runs.data.next_after} busy={runs.isFetching}
      onNext={next => { setRunId(""); cursor.onNext(next); }}
      {...(cursor.onPrevious && { onPrevious: () => { setRunId(""); cursor.onPrevious?.(); } })}
    />
    {selected && <ReviewRoi runId={selected} />}
  </>;
}

export default function AnalyticsPage() {
  const { projectId = "" } = useParams();
  const { stale } = useStream();
  return <section>
    <h1>Аналитика ревью</h1>
    {stale && <p role="status">Данные могут быть устаревшими.</p>}
    <RunSelection key={projectId} projectId={projectId} />
  </section>;
}
