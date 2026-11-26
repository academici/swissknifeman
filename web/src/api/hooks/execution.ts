import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { useStream } from "../../app/providers/StreamProvider";
import { ApiError } from "../errors";
import type { WhoAmIView } from "../generated/access";
import type { ExecutionDetailView } from "../generated/execution-detail";
import type {
  AcceptDeviation, AnswerDecisionRequest, PauseAutopilot, RecordManualVerdict,
} from "../generated/execution_01";
import type { StartAutopilot, StartRun, StopAutopilot } from "../generated/execution_02";
import type { StartRunResult, ValidateForExecutionResult } from "../generated/execution_08";
import type {
  AttemptView, AutopilotExplainView, AutopilotStatusView, DecisionRequestsView, FixBriefView, RunBudgetView, RunView, StepView,
  TaskAttemptsView, TasksView, TaskView,
} from "../generated/execution_10";
import type { Uuid } from "../generated/kernel";
import type { ListEntriesView } from "../generated/settings";
import { newKey, useIdempotentMutation } from "../idempotency";
import { keys } from "../keys";
import { writeSetting } from "./settings";
import { api, segment, sendCommand, useCursor, useRead, withParams, type Command } from "./workspace";

export type ReadRecord = Readonly<Record<string, unknown>>;

export function record(value: unknown): ReadRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as ReadRecord : {};
}

export function field(value: unknown, fallback = "Неизвестно"): string {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  return fallback;
}

export const runPath = (id: string) => `/runs/${segment(id)}`;
export const taskPath = (id: string) => `/tasks/${segment(id)}`;
export const attemptPath = (id: string) => `/attempts/${segment(id)}`;

export function runLink(path: string, projectId: string | null, runId?: string | null) {
  return withParams(path, { project_id: projectId, run_id: runId });
}

function useExecutionSnapshot<T>(queryKey: readonly unknown[], path: string, enabled: boolean) {
  const { transport } = useAuth();
  return useQuery({
    queryKey, enabled,
    queryFn: ({ signal }) => transport.request<T>("GET", api + path, { signal }),
  });
}

export function useRun(runId: string) {
  const { scope } = useScope();
  return useExecutionSnapshot<RunView>(keys.forScope(scope).run(runId), runPath(runId), Boolean(runId));
}

export function useExecutionDetail(kind: "run" | "task" | "attempt", id: string) {
  const { scope } = useScope();
  const scoped = keys.forScope(scope);
  const path = withParams("/execution/detail", { [kind + "_id"]: id });
  const query = useExecutionSnapshot<ExecutionDetailView>([...scoped[kind](id), "metadata"], path, Boolean(id));
  return { ...query, data: query.data?.data, eventsCursor: query.data?.eventsCursor };
}

// Replay from the older of the two reads so changes between snapshots are
// visible. Later GETs leave the reconnection cursor with the transport.
export function useRunEvents(
  runId: string | null, snapshotCursor: number | undefined, metadata: ReturnType<typeof useExecutionDetail>,
  taskId?: string, attemptId?: string,
) {
  const { scope } = useScope();
  const { workspaceId: cacheWorkspace, projectId: cacheProject } = scope;
  const { transport } = useAuth();
  const client = useQueryClient();
  const workspaceId = metadata.data?.workspace_id ?? null;
  const cursor = snapshotCursor === undefined ? undefined : Math.min(snapshotCursor, metadata.eventsCursor ?? snapshotCursor);
  const currentCursor = useEffectEvent(() => cursor);
  const ready = cursor !== undefined;
  useEffect(() => {
    const after = currentCursor();
    if (!runId || !workspaceId || !ready || after === undefined) return;
    const scoped = keys.forScope({ workspaceId: cacheWorkspace, projectId: cacheProject });
    const targets = [
      [...scoped.runRoot(), runId], scoped.runsRoot(),
      ...(taskId ? [scoped.task(taskId)] : []),
      ...(attemptId ? [scoped.attempt(attemptId)] : []),
    ];
    let active = true;
    const refresh = () => {
      for (const queryKey of targets) {
        // Replay can arrive before a related view's first GET completes. Cancel
        // that snapshot so invalidation starts a new read even with an empty cache.
        void client.cancelQueries({ queryKey }).then(() => {
          if (active) return client.invalidateQueries({ queryKey });
        });
      }
    };
    const subscription = transport.events({ workspaceId, streams: [`run:${runId}`], after }, {
      onEvent: event => { if (event.stream_kind === "run" && event.stream_id === runId) refresh(); },
      onSnapshotRequired: refresh,
    });
    return () => {
      active = false;
      subscription.close();
    };
  }, [workspaceId, cacheWorkspace, cacheProject, runId, ready, taskId, attemptId, client, transport]);
}

export function useRunTasks(runId: string, enabled: boolean) {
  const { scope } = useScope();
  return useRead<TasksView>(keys.forScope(scope).runTasks(runId), runPath(runId) + "/tasks", enabled);
}

export function useRunBudget(runId: string) {
  const { scope } = useScope();
  return useRead<RunBudgetView>(keys.forScope(scope).runBudget(runId), runPath(runId) + "/budget");
}

export function useRunRead<T>(runId: string, suffix: string, enabled = true, poll = false) {
  const { scope } = useScope();
  return useRead<T>([...keys.forScope(scope).runRoot(), runId, "views"], runPath(runId) + suffix, enabled, poll);
}

export function useTask(taskId: string) {
  const { scope } = useScope();
  return useExecutionSnapshot<TaskView>(keys.forScope(scope).task(taskId), taskPath(taskId), Boolean(taskId));
}

export function useTaskAttempts(taskId: string) {
  const { scope } = useScope();
  return useRead<TaskAttemptsView>(keys.forScope(scope).task(taskId), taskPath(taskId) + "/attempts", Boolean(taskId));
}

export function useAttempt(attemptId: string) {
  const { scope } = useScope();
  return useExecutionSnapshot<AttemptView>(keys.forScope(scope).attempt(attemptId), attemptPath(attemptId), Boolean(attemptId));
}

export function useStep(stepId: string, enabled = true, attemptId?: string) {
  const { scope } = useScope();
  const key = attemptId ? keys.forScope(scope).attempt(attemptId) : keys.scope(scope);
  return useRead<StepView>(key, `/steps/${segment(stepId)}`, enabled && Boolean(stepId));
}

export function useFixBrief(id: string) {
  const { scope } = useScope();
  return useRead<FixBriefView>(keys.scope(scope), `/fix-briefs/${segment(id)}`);
}

type StartInputs = Pick<StartRun, "overrides" | "selection">;

export function useStartRun(planId: string, revisionId: string) {
  const plan = `/plans/${segment(planId)}`;
  const validate = useExecutionCommand<ValidateForExecutionResult>();
  const start = useExecutionCommand<StartRunResult>();
  return {
    validate: (body: StartInputs) => validate.mutateAsync({
      path: `${plan}/revisions/${segment(revisionId)}/readiness`, body,
    }),
    start: (body: StartInputs & Pick<StartRun, "reason" | "readiness_report_id">) => start.mutateAsync({
      path: plan + "/runs", body: { ...body, revision_id: revisionId },
    }),
  };
}

interface ExecutionCommand {
  path: string;
  body: ReadRecord;
  ifMatch?: string;
}

export function useExecutionCommand<T = unknown>() {
  const { transport } = useAuth();
  const { scope } = useScope();
  const client = useQueryClient();
  const pendingKeys = useRef(new Map<string, string>());
  const fingerprint = ({ path, body, ifMatch }: ExecutionCommand) => JSON.stringify([path, body, ifMatch]);
  return useMutation({
    mutationFn: (command: ExecutionCommand) => {
      const { path, body, ifMatch } = command;
      const input = fingerprint(command);
      const idempotencyKey = pendingKeys.current.get(input) ?? newKey();
      pendingKeys.current.set(input, idempotencyKey);
      return transport.request<T>("POST", api + path, {
        body, ...(ifMatch === undefined ? {} : { ifMatch }), idempotencyKey,
      });
    },
    retry: false,
    onSuccess: (_result, command) => {
      pendingKeys.current.delete(fingerprint(command));
      if (command.path.endsWith("/readiness")) return;
      const scoped = keys.forScope(scope);
      for (const queryKey of [scoped.runRoot(), scoped.runsRoot(), scoped.tasksRoot(), scoped.attemptsRoot()]) {
        void client.invalidateQueries({ queryKey });
      }
    },
  });
}

const enabledKey = "execution.autopilot.enabled";
const autopilotPath = (id: string) => "/projects/" + segment(id) + "/autopilot";

export function useAutopilot(projectId: string) {
  const { scope: { workspaceId } } = useScope();
  const scoped = keys.forScope({ projectId, workspaceId });
  const key = scoped.autopilot(projectId);
  const path = autopilotPath(projectId);
  const status = useRead<AutopilotStatusView>([...key, "status"], path, Boolean(projectId));
  const explain = useRead<AutopilotExplainView>([...key, "explain"], path + "/explain", Boolean(projectId));
  return { status, explain };
}

export function useAutopilotEntry(projectId: string, enabled: boolean) {
  const { scope } = useScope();
  const target = "project:" + projectId;
  return useRead<ListEntriesView>(keys.forScope(scope).configExplain(target),
    withParams("/config/entries", { scope: target, key_prefix: enabledKey }), enabled);
}

export type AutopilotAction =
  | { action: "start"; body: Omit<StartAutopilot, "project_id"> }
  | { action: "pause" | "drain"; body: Pick<PauseAutopilot, "reason"> }
  | { action: "stop"; body: Omit<StopAutopilot, "project_id"> }
  | { action: "configure"; value: boolean; version: number | null; reason: string };

export function useAutopilotCommand(projectId: string) {
  const client = useQueryClient();
  const { transport } = useAuth();
  const { scope } = useScope();
  const scoped = keys.forScope({ workspaceId: scope.workspaceId, projectId });
  const attemptedKey = useRef<string>(undefined);
  return useIdempotentMutation(async (command: AutopilotAction, idempotencyKey) => {
    if (attemptedKey.current === idempotencyKey) {
      const permission = command.action === "configure" ? "config.write" : "run.control";
      const path = api + withParams("/me", { scope_id: projectId });
      const { data, requestId } = await transport.request<WhoAmIView>("GET", path);
      if (!data.effective_permissions.includes(permission)) {
        throw ApiError.fromResponse(403, { code: "FORBIDDEN", category: "forbidden", details: { permission } }, requestId, path);
      }
    }
    attemptedKey.current = idempotencyKey;
    try {
      if (command.action === "configure") {
        await writeSetting(transport, {
          op: "set", scope: { level: "project", scope_id: projectId as Uuid }, key: enabledKey,
          version: command.version, value: command.value, reason: command.reason, confirmed: true,
        }, idempotencyKey);
      } else {
        await transport.request("POST", api + autopilotPath(projectId) + "/" + command.action, {
          body: command.body, idempotencyKey,
        });
      }
    } finally {
      void client.invalidateQueries({ queryKey: scoped.autopilot(projectId) });
      if (command.action === "configure") {
        void client.invalidateQueries({ queryKey: [...keys.scope(scope), "config", "project:" + projectId] });
      }
    }
  });
}

export const decisionStates = ["open", "answered", "applied", "assumed", "denied", "stale", "expired", "cancelled"] as const;
export type DecisionRequest = DecisionRequestsView["items"][number];
export const inboxScopePattern = "(?:project|run):[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}";
const explicitInboxScope = new RegExp(`^${inboxScopePattern}$`, "u");

export function inboxTarget(explicit: string | null, projectId: string | null): string | null {
  if (explicit !== null) return explicitInboxScope.test(explicit) ? explicit : null;
  return projectId === null ? null : `project:${projectId}`;
}

export function useInboxRequests(target: string | null, kind: string, state: string, followEvents = true) {
  const { scope } = useScope();
  const { transport } = useAuth();
  const { readWithEvents } = useStream();
  const cursor = useCursor(withParams("/inbox", {
    scope: target,
    kinds: kind === "all" ? null : kind === "deviation" ? "escalation" : kind,
    states: state === "all" ? decisionStates.join(",") : state,
  }));
  const query = useQuery({
    queryKey: [...keys.forScope(scope).inbox(), cursor.path, followEvents],
    enabled: target !== null,
    queryFn: async ({ signal }) => {
      const read = () => transport.request<DecisionRequestsView>("GET", api + cursor.path, { signal });
      return (followEvents ? await readWithEvents(read, signal) : await read()).data;
    },
  });
  return { query, cursor };
}

export function useInboxPermissions(scopeId: string | null) {
  const { me, transport } = useAuth();
  const known = scopeId ? me?.permissions_by_scope[scopeId] : undefined;
  const query = useQuery({
    queryKey: ["access", "permissions", scopeId],
    enabled: me?.principal.kind === "human" && Boolean(scopeId) && known === undefined,
    queryFn: async ({ signal }) => (await transport.request<WhoAmIView>(
      "GET", api + withParams("/me", { scope_id: scopeId }), { signal },
    )).data.effective_permissions,
  });
  const permissions = known ?? query.data;
  return (permission: string) => me?.principal.kind === "human" && permissions?.includes(permission) === true;
}

type InboxSubmission = { command: Command; key: string; runId?: string };

function pendingInboxSubmission(storageKey: string): InboxSubmission | null {
  try {
    return JSON.parse(sessionStorage.getItem(storageKey) ?? "null") as InboxSubmission | null;
  } catch {
    return null;
  }
}

function saveInboxSubmission(storageKey: string, submission: InboxSubmission | null) {
  try {
    if (submission) sessionStorage.setItem(storageKey, JSON.stringify(submission));
    else sessionStorage.removeItem(storageKey);
  } catch {
    // The mounted form can still replay its submission if session storage is unavailable.
  }
}

export function useInboxCommand<T>(operation: string, resourceId: string) {
  const { me, transport } = useAuth();
  const { scope } = useScope();
  const client = useQueryClient();
  const storageKey = `skm.inbox.pending:${me?.principal.principal_id}:${operation}:${resourceId}`;
  const [pending, setPending] = useState(() => pendingInboxSubmission(storageKey));

  function settle(submission: InboxSubmission) {
    if (pendingInboxSubmission(storageKey)?.key === submission.key) saveInboxSubmission(storageKey, null);
    setPending(current => current?.key === submission.key ? null : current);
  }

  const mutation = useMutation({
    mutationFn: ({ command, key }: InboxSubmission) =>
      sendCommand<T>(transport, command, key),
    retry: false,
    networkMode: "always",
    onError: (error, submission) => {
      if (error instanceof ApiError && !error.retryable && error.status >= 400 &&
          error.status < 500 && error.status !== 408) settle(submission);
    },
    onSuccess: (_result, submission) => {
      settle(submission);
      const { runId } = submission;
      const scoped = keys.forScope(scope);
      void client.invalidateQueries({ queryKey: scoped.inbox() });
      if (runId) {
        void client.invalidateQueries({ queryKey: [...scoped.runRoot(), runId] });
        void client.invalidateQueries({ queryKey: scoped.runsRoot() });
      }
    },
  });
  const awaitsResult = pending !== null && !mutation.isSuccess;
  return {
    status: awaitsResult && mutation.isIdle ? "error" as const : mutation.status,
    error: mutation.error ?? (awaitsResult && !mutation.isPending ? new Error("Результат отправки неизвестен") : null),
    isPending: mutation.isPending,
    awaitsResult,
    reset: () => { if (!awaitsResult) mutation.reset(); },
    reconcile: () => {
      if (pending && !mutation.isPending) settle(pending);
      mutation.reset();
    },
    submit: (command: Command, runId?: string) => {
      if (!mutation.isIdle || pending !== null || pendingInboxSubmission(storageKey) !== null) return;
      const submission = { command, key: newKey(), ...(runId ? { runId } : {}) };
      saveInboxSubmission(storageKey, submission);
      setPending(submission);
      mutation.mutate(submission);
    },
    retry: () => {
      if (pending && !mutation.isPending) mutation.mutate(pending);
    },
  };
}

export function useAnswerDecision(runId: string, requestId: string) {
  const mutation = useInboxCommand<import("../generated/execution_08").AnswerDecisionRequestResult>("answer", requestId);
  return {
    ...mutation,
    answer: (body: AnswerDecisionRequest) =>
      mutation.submit({ path: `/decision-requests/${segment(body.request_id)}/answer`, body }, runId),
  };
}

export function useRecordManualVerdict(runId: string, checkId: string) {
  const mutation = useInboxCommand<import("../generated/execution_08").RecordManualVerdictResult>("verdict", checkId);
  return {
    ...mutation,
    recordVerdict: (body: RecordManualVerdict) =>
      mutation.submit({ path: `/check-executions/${segment(body.check_execution_id)}/verdict`, body }, runId),
  };
}

export function useAcceptDeviation(runId: string, requestId: string) {
  const mutation = useInboxCommand<import("../generated/execution_08").AcceptDeviationResult>("deviation", requestId);
  return {
    ...mutation,
    accept: (body: AcceptDeviation) => mutation.submit({ path: "/deviations", body }, runId),
  };
}
