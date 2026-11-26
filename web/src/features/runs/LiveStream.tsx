import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useState } from "react";
import { ApiError } from "../../api/errors";
import type { AttemptView } from "../../api/generated/execution_10";
import type { SessionEvent } from "../../api/generated/runtimes";
import type { ExplainReport } from "../../api/generated/settings";
import { useBlobTransport } from "../../api/hooks/artifacts";
import { useStep } from "../../api/hooks/execution";
import { api, withParams } from "../../api/hooks/workspace";
import { attemptLiveSetting, invalidateEvent } from "../../api/invalidation";
import { keys } from "../../api/keys";
import { subscribeAttempt, type LiveGap } from "../../api/live";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { useStream } from "../../app/providers/StreamProvider";
import { CodeBlock } from "../../components/content/CodeBlock";
import { ErrorPanel } from "../../components/feedback/ErrorPanel";
import { Button } from "../../components/primitives/Button";
import { Skeleton } from "../../components/primitives/Skeleton";
import { escapeText } from "../../lib/safeText";

function TranscriptContent({ versionId, stepId }: { versionId: string; stepId: string }) {
  const files = useBlobTransport();
  const [text, setText] = useState<string>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(false);

  async function open() {
    setLoading(true);
    setText(undefined);
    setError(undefined);
    try {
      const blob = await files.content(versionId);
      setText(await blob.text());
    } catch (failure) {
      setError(failure);
    } finally {
      setLoading(false);
    }
  }
  return <>
    <Button disabled={loading} onClick={() => { void open(); }}>Открыть транскрипт шага {escapeText(stepId)}</Button>
    {text !== undefined && <CodeBlock text={text} />}
    {error != null && <ErrorPanel error={error} />}
  </>;
}

function StepTranscript({ stepId, attemptId }: { stepId: string; attemptId: string }) {
  const step = useStep(stepId, true, attemptId);
  if (step.isError) return <ErrorPanel error={step.error} onRetry={() => void step.refetch()} />;
  if (!step.data) return <Skeleton />;
  const { payload_visibility, transcript_file_version_id } = step.data;
  return payload_visibility === "available" && transcript_file_version_id
    ? <TranscriptContent key={transcript_file_version_id} versionId={transcript_file_version_id} stepId={stepId} />
    : <p>Транскрипт шага {escapeText(stepId)} недоступен.</p>;
}

function describe(event: SessionEvent): string {
  switch (event.type) {
    case "text_delta": return event.channel + " · " + event.text;
    case "session_started": return [event.model, event.runtime_version, event.session_ref].filter(Boolean).join(" · ");
    case "tool_requested": return [event.tool, event.call_id, event.args_preview].join(" · ");
    case "tool_completed": return [event.call_id, event.status, event.duration_ms == null ? "—" : event.duration_ms + " мс"].join(" · ");
    case "usage_reported": return JSON.stringify(event.usage);
    case "checkpoint_available": return event.session_ref;
    case "cancel_ignored": return event.signal;
    case "session_completed": return event.stop_reason;
    case "session_failed": return event.failure.code + " · " + event.failure.safe_message;
  }
}

type LiveProps = {
  attempt: Pick<AttemptView, "attempt_id" | "finished_at" | "steps">;
  projectId: string | null;
  workspaceId: string | null;
};
const maxVisibleEvents = 2000;

function AttemptStream({ attempt }: Pick<LiveProps, "attempt">) {
  const { token, mode, status, signOut, sessionGeneration } = useAuth();
  const { scope } = useScope();
  const client = useQueryClient();
  const id = attempt.attempt_id;
  const active = attempt.finished_at === null;
  const [ended, setEnded] = useState(false);
  const [connection, setConnection] = useState("Подключение…");
  const [gap, setGap] = useState<LiveGap>();
  const [error, setError] = useState<Error>();
  const [events, setEvents] = useState<readonly SessionEvent[]>([]);
  const finish = useEffectEvent(() => {
    setEnded(true);
    void client.invalidateQueries({ queryKey: keys.forScope(scope).attempt(id) });
  });
  const cookieSession = status === "authenticated" && (mode === "admin_login" || mode === "none");
  useEffect(() => {
    if ((!token && !cookieSession) || !active || ended) return;
    const feed = subscribeAttempt(id, token ? token : { token: null, credentials: "include" }, {
      onConnection: connected => setConnection(connected ? "В эфире" : "Связь прервана. Переподключение…"),
      onEvent: event => setEvents(previous => [...previous.slice(1 - maxVisibleEvents), event]),
      onGap: setGap,
      onEnd: finish,
      onError: setError,
      onUnauthorized: () => { void signOut(sessionGeneration); },
    });
    return () => feed.close();
  }, [active, cookieSession, ended, id, sessionGeneration, signOut, token]);

  if ((!token && !cookieSession) || (error instanceof ApiError && [403, 404].includes(error.status))) return null;
  return <section aria-label="Прямой эфир попытки">
    <h2>Прямой эфир попытки</h2>
    {error ? <ErrorPanel error={error} /> : <p role="status">{ended || !active ? "Поток завершён" : connection}</p>}
    {gap && <p role="alert">Пропуск событий · {escapeText(gap.reason)} · после {gap.after}
      {gap.oldest !== null && <> · доступны с {gap.oldest}</>}
    </p>}
    {events.length > 0 && <ol aria-label="События попытки">{events.map((event, index) =>
      <li key={index}><strong>{escapeText(event.type)}</strong> {escapeText(describe(event))}</li>)}</ol>}
    {(gap || ended || !active || error) && <section aria-label="Сохранённые транскрипты">
      <h3>Сохранённые транскрипты</h3>
      {!attempt.steps.length && <p>Пока нет шагов с транскриптом.</p>}
      {attempt.steps.map(step => typeof step.step_id === "string" &&
        <StepTranscript key={step.step_id} stepId={step.step_id} attemptId={id} />)}
    </section>}
  </section>;
}

function useLiveSetting(active: boolean, projectId: string | null, workspaceId: string | null) {
  const { transport } = useAuth();
  const { scope } = useScope();
  const client = useQueryClient();
  const { readWithEvents } = useStream();
  const sameWorkspace = workspaceId === scope.workspaceId;
  const target = "project:" + projectId;
  const owner = { workspaceId, projectId };
  const queryKey = [...keys.scope(owner), "config", target, attemptLiveSetting];
  const setting = useQuery({
    queryKey,
    enabled: active && workspaceId !== null && projectId !== null,
    queryFn: async ({ signal }) => {
      const path = withParams("/config/effective", { scope: target, keys: attemptLiveSetting });
      const read = () => transport.request<ExplainReport>("GET", api + path, { signal });
      // The shell cursor belongs to its selected workspace, even on a bare attempt URL.
      return sameWorkspace ? readWithEvents(read, signal) : read();
    },
    refetchOnMount: "always",
    // Instance-level changes are outside the workspace event feed.
    refetchInterval: 30_000,
  });
  const cursor = setting.data?.eventsCursor;
  const currentCursor = useEffectEvent(() => cursor);
  const watchConfig = active && !sameWorkspace && cursor !== undefined;
  const refresh = useEffectEvent(() => { void client.invalidateQueries({ queryKey }); });
  useEffect(() => {
    if (!watchConfig || workspaceId === null || projectId === null) return;
    const after = currentCursor();
    if (after === undefined) return;
    const feed = transport.events({ workspaceId, after, streams: [`config:${workspaceId}`, `config:${projectId}`] }, {
      onEvent: event => invalidateEvent(client, { workspaceId, projectId }, event),
      onSnapshotRequired: () => refresh(),
    });
    return () => feed.close();
  }, [watchConfig, workspaceId, projectId, transport, client]);
  return setting;
}

export function LiveStream({ attempt, projectId, workspaceId }: LiveProps) {
  const active = attempt.finished_at === null;
  const setting = useLiveSetting(active, projectId, workspaceId);
  if (active && setting.isError) return <ErrorPanel error={setting.error} onRetry={() => void setting.refetch()} />;
  if (active && setting.data?.data.keys.find(row => row.key === attemptLiveSetting)?.value !== true) return null;
  return <AttemptStream key={attempt.attempt_id} attempt={attempt} />;
}
