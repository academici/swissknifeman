import { useId, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../../api/errors";
import type { StartRun } from "../../api/generated/execution_02";
import type { ValidateForExecutionResult } from "../../api/generated/execution_08";
import { field, runLink, runPath, useStartRun } from "../../api/hooks/execution";
import { SafeLink } from "../../components/content/SafeLink";
import { KeyValue } from "../../components/data/KeyValue";
import { JsonView } from "../../components/data/JsonView";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Dialog } from "../../components/primitives/Dialog";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";
import { TokenBudgetPreview, WorkPolicy } from "./BudgetPanel";

interface Props {
  open: boolean;
  onClose(): void;
  planId: string;
  revisionId: string;
  projectId: string | null;
}

function split(value: string) {
  return value.split(",").map(item => item.trim()).filter(Boolean);
}

export default function StartRunDialog(props: Props) {
  return props.open ? <StartRunForm key={JSON.stringify([props.planId, props.revisionId])} {...props} /> : null;
}

function StartRunForm({ onClose, planId, revisionId, projectId }: Props) {
  const [overrides, setOverrides] = useState("{}");
  const [tasks, setTasks] = useState("");
  const [phases, setPhases] = useState("");
  const [stopAfter, setStopAfter] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<"validate" | "start" | null>(null);
  const [report, setReport] = useState<{
    data: ValidateForExecutionResult;
    inputs: Pick<StartRun, "overrides" | "selection">;
  } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [inputError, setInputError] = useState(false);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const formId = useId();
  const navigate = useNavigate();
  const command = useStartRun(planId, revisionId);
  const ready = report?.data.status === "ready" || report?.data.status === "ready_with_advisories";

  function edit(setValue: (value: string) => void, value: string) {
    generation.current += 1;
    setValue(value);
    setReport(null);
    setError(null);
    setInputError(false);
  }

  async function validate() {
    if (inFlight.current) return;
    setReport(null);
    setError(null);
    setInputError(false);
    let parsed: StartRun["overrides"];
    try {
      const value: unknown = JSON.parse(overrides);
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error();
      parsed = value as StartRun["overrides"];
    } catch {
      setInputError(true);
      return;
    }

    const taskKeys = split(tasks);
    const phaseKeys = split(phases);
    const stop = stopAfter.trim();
    const selection = {
      ...(taskKeys.length ? { task_keys: taskKeys } : {}),
      ...(phaseKeys.length ? { phases: phaseKeys } : {}),
      ...(stop ? { stop_after: stop } : {}),
    };
    const inputs = { overrides: parsed, ...(Object.keys(selection).length ? { selection } : {}) };
    const validatedGeneration = generation.current;
    inFlight.current = true;
    setPending("validate");
    try {
      const { data } = await command.validate(inputs);
      if (generation.current === validatedGeneration) setReport({ data, inputs });
    } catch (failure) {
      if (generation.current === validatedGeneration) setError(failure);
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }

  async function start() {
    if (inFlight.current || !ready || !report?.data.report_id || !reason.trim()) return;
    inFlight.current = true;
    setPending("start");
    setError(null);
    try {
      const { data } = await command.start({
        ...report.inputs, reason: reason.trim(), readiness_report_id: report.data.report_id,
      });
      onClose();
      void navigate(runLink(runPath(data.run_id), projectId));
    } catch (failure) {
      setError(failure);
      if (failure instanceof ApiError && failure.code === "READINESS_REQUIRED") setReport(null);
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }

  return <Dialog open title="Новый запуск" onClose={() => {
    if (!inFlight.current) onClose();
  }}>
    <p>Ревизия <code>{escapeText(revisionId)}</code></p>
    <form onSubmit={event => { event.preventDefault(); void start(); }}>
      <fieldset disabled={pending === "start"}>
        <legend>Параметры запуска</legend>
        <label htmlFor={formId + "-overrides"}>Переопределения запуска (JSON)</label>
        <textarea id={formId + "-overrides"} value={overrides} onChange={event => edit(setOverrides, event.target.value)} />
        {inputError && <p role="alert">Введите JSON-объект с переопределениями.</p>}
        <label htmlFor={formId + "-tasks"}>Ключи задач через запятую</label>
        <input id={formId + "-tasks"} value={tasks} onChange={event => edit(setTasks, event.target.value)} />
        <label htmlFor={formId + "-phases"}>Фазы через запятую</label>
        <input id={formId + "-phases"} value={phases} onChange={event => edit(setPhases, event.target.value)} />
        <label htmlFor={formId + "-stop"}>Остановиться после задачи</label>
        <input id={formId + "-stop"} value={stopAfter} onChange={event => edit(setStopAfter, event.target.value)} />
      </fieldset>
      <Button disabled={pending !== null} onClick={() => { void validate(); }}>Проверить готовность</Button>
      {pending === "validate" && <p role="status">Проверка готовности…</p>}
      {report && <section aria-label="Отчёт о готовности">
        <h2>Готовность <StatusBadge status={report.data.status} /></h2>
        <ul>{report.data.findings.map((finding, index) => <li key={index}>
          <StatusBadge status={field(finding.severity)} /> {escapeText(field(finding.message ?? finding.code))}
          <JsonView value={finding} />
        </li>)}</ul>
        {report.data.audit_run_id && <SafeLink href={runLink(runPath(report.data.audit_run_id), projectId)}>Запуск аудита</SafeLink>}
        <h3>Оценка</h3>
        <dl>{Object.entries(report.data.estimate).filter(([key]) => key !== "token_budget").map(([key, value]) => <KeyValue key={key}
          label={key} value={value !== null && typeof value === "object" ? <JsonView value={value} /> : field(value)}
        />)}</dl>
        <TokenBudgetPreview value={report.data.estimate.token_budget} />
        <h3>Политики интенсивности</h3>
        {Object.entries(report.data.work_policies).map(([key, policy]) => <details key={key}>
          <summary>{escapeText(key)}</summary>
          <WorkPolicy policy={policy} />
        </details>)}
      </section>}
      <label htmlFor={formId + "-reason"}>Причина</label>
      <textarea id={formId + "-reason"} value={reason} onChange={event => setReason(event.target.value)} required disabled={pending === "start"} />
      {error != null && <ErrorPanel error={error} />}
      <Button type="submit" disabled={!ready || pending !== null || !reason.trim()}>Запустить</Button>
      {pending === "start" && <p role="status">Запуск…</p>}
    </form>
  </Dialog>;
}
