import { useState } from "react";
import type { StepView } from "../../api/generated/execution_10";
import { downloadBlob, useBlobTransport } from "../../api/hooks/artifacts";
import { field, record, runLink, useStep, type ReadRecord } from "../../api/hooks/execution";
import { segment } from "../../api/hooks/workspace";
import { SafeLink } from "../../components/content/SafeLink";
import { JsonView } from "../../components/data/JsonView";
import { KeyValue } from "../../components/data/KeyValue";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { StatusBadge } from "../../components/primitives/StatusBadge";
import { escapeText } from "../../lib/safeText";

export function FileDownload({ versionId, label }: { versionId: string; label: string }) {
  const files = useBlobTransport();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const blob = await files.content(versionId);
      downloadBlob(blob, `skm-${versionId.replace(/[^a-z0-9-]/giu, "_")}.download`);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }

  return <>
    <Button disabled={busy} onClick={() => { void download(); }}>{label}</Button>
    {error != null && <ErrorPanel error={error} />}
  </>;
}

function names(value: unknown) {
  return Array.isArray(value) ? value.map(item => field(item)).join(", ") || "Нет" : "Неизвестно";
}

function Telemetry({ step }: { step: StepView }) {
  const observation = record(step.runtime_observation);
  const binding = record(observation.binding);
  const timing = record(observation.timing);
  const capture = record(observation.capture);
  const tools = record(observation.tools);
  const usage = record(step.usage);
  const subagents = record(usage.subagents);
  const route = record(step.route_snapshot);
  const requested = record(route.requested);

  return <>
    <h3>Привязка модели</h3>
    <dl>
      <KeyValue label="Запрошенный маршрут" value={field(requested.runtime_id)} />
      <KeyValue label="Запрошенная модель" value={field(requested.model)} />
      <KeyValue label="Запрошенный класс модели" value={field(requested.model_class)} />
      <KeyValue label="Запрошенный effort" value={field(requested.effort)} />
      <KeyValue label="Выбранный effort" value={field(record(route.resolved).effort)} />
      <KeyValue label="Выбранная среда" value={step.runtime_id} />
      <KeyValue label="Выбранная модель" value={step.model} />
      <KeyValue label="Модель по сообщению провайдера" value={field(binding.provider_reported_model)} />
      <KeyValue label="Источник сообщения о модели" value={field(binding.model_source)} />
      <KeyValue label="Причина выбора маршрута" value={step.route_reason} />
      <KeyValue label="Режим сессии" value={step.session_mode} />
    </dl>
    {step.route_snapshot && <JsonView value={step.route_snapshot} />}
    <h3>Время</h3>
    <dl>
      <KeyValue label="Основа измерения" value={field(timing.basis,
        timing.duration_ms != null && timing.clock_domain_id != null ? "Монотонные часы процесса" : "Неизвестно")} />
      <KeyValue label="Длительность, мс" value={field(timing.duration_ms)} />
      <KeyValue label="Часы процесса" value={field(timing.clock_domain_id)} />
      <KeyValue label="Первое наблюдение хоста" value={field(timing.first_observed_at)} />
      <KeyValue label="Последнее наблюдение хоста" value={field(timing.last_observed_at)} />
      <KeyValue label="Первое время провайдера" value={field(timing.provider_first_at)} />
      <KeyValue label="Последнее время провайдера" value={field(timing.provider_last_at)} />
    </dl>
    <h3>Захват данных</h3>
    <dl>
      <KeyValue label="Полнота захвата" value={field(capture.coverage, "Недоступно")} />
      <KeyValue label="Данные усечены" value={field(capture.truncated)} />
      <KeyValue label="Пропуски" value={names(capture.gaps)} />
      <KeyValue label="Отметки парсера" value={names(capture.parser_flags)} />
    </dl>
    {observation.capture != null && <JsonView value={observation.capture} />}
    <h3>Инструменты</h3>
    <dl>
      <KeyValue label="Полнота наблюдения инструментов" value={field(tools.coverage, "Недоступно")} />
      <KeyValue label="Наблюдаемые вызовы" value={tools.coverage === "unavailable" ? "Неизвестно" : field(tools.observed_calls)} />
    </dl>
    <h3>Расход</h3>
    <dl>
      <KeyValue label="Статус учёта" value={field(usage.status, "unknown")} />
      {([
        ["input_tokens", "Входные токены"], ["output_tokens", "Выходные токены"],
        ["cache_read_tokens", "Токены чтения кэша"], ["cache_write_tokens", "Токены записи кэша"],
        ["reasoning_tokens", "Токены рассуждения"], ["cost_usd_micros", "Стоимость, миллионные доли USD"],
      ] as const).map(([id, label]) => <KeyValue key={id} label={label}
        value={usage.status === "unknown" ? "Неизвестно" : field(usage[id])} />)}
      <KeyValue label="Субагенты использовались" value={field(subagents.used)} />
      <KeyValue label="Данные о субагентах раскрыты" value={field(subagents.disclosed)} />
      <KeyValue label="Источник расхода" value={field(usage.source)} />
    </dl>
  </>;
}

function StepDetails({ stepId, attemptId, projectId }: { stepId: string; attemptId: string; projectId: string | null }) {
  const step = useStep(stepId, true, attemptId);
  if (step.isError) return <ErrorPanel error={step.error} onRetry={() => { void step.refetch(); }} />;
  if (!step.data) return <Skeleton />;
  const data = step.data;
  return <>
    <Telemetry step={data} />
    {data.context_manifest_id && <SafeLink href={runLink(`/steps/${segment(stepId)}/context`, projectId)}>Контекст шага</SafeLink>}
    <dl><KeyValue label="Доступность материалов" value={field(data.payload_visibility, "Недоступно")} /></dl>
    {data.payload_visibility === "available" && <>
      {data.transcript_file_version_id && <FileDownload versionId={data.transcript_file_version_id} label="Скачать транскрипт" />}
      {data.raw_result_file_version_id && <FileDownload versionId={data.raw_result_file_version_id} label="Скачать исходный результат" />}
      {data.result && <JsonView value={data.result} />}
    </>}
    {data.repairs?.length > 0 && <JsonView value={data.repairs} />}
    {data.schema_errors?.length > 0 && <JsonView value={data.schema_errors} />}
  </>;
}

export function StepPanel({ step, attemptId, projectId }: { step: ReadRecord; attemptId: string; projectId: string | null }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{escapeText(field(step.role))} · {escapeText(field(step.purpose))} <StatusBadge status={field(step.state)} /></summary>
    {open && typeof step.step_id === "string" && <StepDetails stepId={step.step_id} attemptId={attemptId} projectId={projectId} />}
  </details>;
}
