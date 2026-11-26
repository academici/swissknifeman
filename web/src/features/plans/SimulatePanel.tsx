import { useState } from "react";
import type { SimulationViewDefsRange } from "../../api/generated/planning";
import { useSimulation, type PlanSource } from "../../api/hooks/planning";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";

const number = new Intl.NumberFormat("ru");
const dollars = new Intl.NumberFormat("ru", { maximumFractionDigits: 6 });
function range(value: SimulationViewDefsRange | null, formatter: Intl.NumberFormat, divisor = 1) {
  return value == null ? "unknown" : `${formatter.format(value.min / divisor)}–${formatter.format(value.max / divisor)}`;
}

export default function SimulatePanel({ planId, source }: { planId: string; source: PlanSource }) {
  const [rate, setRate] = useState("");
  const [applied, setApplied] = useState<number>();
  const simulation = useSimulation(planId, source, applied);
  const data = simulation.data;
  return <section aria-label="Симуляция плана">
    <form onSubmit={event => {
      event.preventDefault();
      const next = rate ? Number(rate) : undefined;
      if (next === applied) void simulation.refetch();
      else setApplied(next);
    }}>
      <label>Предполагаемая скорость (токенов/с) <input type="number" min={1} max={1000000} step={1}
        value={rate} onChange={event => setRate(event.target.value)} /></label>
      <Button type="submit" disabled={simulation.isFetching}>Рассчитать</Button>
    </form>
    {simulation.error ? <ErrorPanel error={simulation.error} onRetry={() => void simulation.refetch()} /> : data ? <>
      <p>Основание оценки — <code>{data.basis}</code>. Один вызов модели на задачу, без ожидания и повторов.</p>
      <dl>
        <dt>Задачи</dt><dd>{number.format(data.task_count)}</dd>
        <dt>Токены</dt><dd>{range(data.tokens, number)}</dd>
        <dt>Стоимость (USD)</dt><dd>{range(data.cost_usd_micros, dollars, 1_000_000)}</dd>
        <dt>Суммарное время работы моделей (с)</dt><dd>{range(data.duration_seconds, number)}</dd>
        {data.tokens_per_second != null && <><dt>Скорость (токенов/с)</dt><dd>{number.format(data.tokens_per_second)}</dd></>}
      </dl>
    </> : <Skeleton />}
  </section>;
}
