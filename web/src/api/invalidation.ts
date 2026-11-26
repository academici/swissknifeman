import type { Query, QueryClient, QueryKey } from "@tanstack/react-query";
import type { EventEnvelope } from "./generated/kernel";
import { keys, type QueryScope } from "./keys";

type Notice = { message: string; requestId?: string };

export const attemptLiveSetting = "ui.runs.live_stream";

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function shortName(type: string): string {
  const name = /^urn:skm:[a-z][a-z0-9-]*:event:([a-z][a-z0-9-]*):v[1-9][0-9]*$/u.exec(type)?.[1];
  return name?.replace(/(?:^|-)([a-z0-9])/gu, (_, first: string) => first.toUpperCase()) ?? type;
}

function configScope(value: unknown): string | undefined {
  if (typeof value === "string") {
    return /^(workspace|project|plan|run):[^:]+$/u.test(value) ? value : undefined;
  }
  if (typeof value !== "object" || value === null || !("level" in value) || !("scope_id" in value)) return;
  const { level, scope_id: scopeId } = value;
  if ((level === "workspace" || level === "project" || level === "plan" || level === "run") && nonEmptyString(scopeId)) {
    return `${level}:${scopeId}`;
  }
}

function isPreview(query: Query, draftRoot: QueryKey): boolean {
  return query.queryKey[draftRoot.length + 1] === "publication-preview";
}

function field(value: unknown, key: string): unknown {
  return typeof value === "object" && value !== null && key in value
    ? (value as Record<string, unknown>)[key]
    : undefined;
}

function rows(value: unknown, key: string): readonly unknown[] {
  const result = field(value, key);
  return Array.isArray(result) ? result : [];
}

function containsId(value: unknown, list: string, key: string, id: string | undefined): boolean {
  return id !== undefined && rows(value, list).some((row) => field(row, key) === id);
}

type ScopedKeys = ReturnType<typeof keys.forScope>;

function taskForAttempt(client: QueryClient, scoped: ScopedKeys, attempt: string | undefined) {
  const root = scoped.tasksRoot();
  const match = client.getQueriesData({ queryKey: root }).find(([, data]) =>
    containsId(data, "attempts", "attempt_id", attempt));
  return nonEmptyString(match?.[0][root.length]);
}

function attemptForReview(client: QueryClient, scoped: ScopedKeys, task: string | undefined, payload: EventEnvelope["payload"]) {
  const output = nonEmptyString(payload.output_id);
  const review = nonEmptyString(payload.review_id);
  if (task) {
    for (const [, data] of client.getQueriesData({ queryKey: scoped.task(task) })) {
      const match = rows(data, "attempts").find((attempt) => containsId(attempt, "outputs", "output_id", output));
      const id = nonEmptyString(field(match, "attempt_id"));
      if (id) return id;
    }
  }
  const root = scoped.attemptsRoot();
  const match = client.getQueriesData({ queryKey: root }).find(([, data]) =>
    containsId(data, "outputs", "output_id", output) || containsId(data, "reviews", "review_id", review));
  return nonEmptyString(match?.[0][root.length]);
}

function runsForIntent(client: QueryClient, scoped: ScopedKeys, payload: EventEnvelope["payload"], intent: string): Set<string> {
  const result = new Set<string>();
  const runRoot = scoped.runRoot();
  const scopeId = nonEmptyString(payload.scope_id);
  // Policy scope IDs can name resources other than runs. Confirm the relationship in the cache.
  if (scopeId && client.getQueriesData({ queryKey: [...runRoot, scopeId] }).length) result.add(scopeId);
  for (const [, data] of client.getQueriesData({ queryKey: scoped.inbox() })) {
    for (const item of rows(data, "items")) {
      const run = nonEmptyString(field(item, "run_id"));
      if (run && field(field(item, "payload"), "intent_id") === intent) result.add(run);
    }
  }
  for (const [key, data] of client.getQueriesData({ queryKey: runRoot })) {
    const run = nonEmptyString(key[runRoot.length]);
    if (run && key[runRoot.length + 1] === "tasks" && rows(data, "tasks").some((task) =>
      field(field(field(task, "blocking_reason"), "refs"), "intent_id") === intent)) result.add(run);
  }
  return result;
}

/** Apply the web event map within the active query namespace. */
export function invalidateEvent(
  queryClient: QueryClient, scope: QueryScope, event: EventEnvelope, toast?: (notice: Notice) => void,
): void {
  const { payload, stream_kind: kind, stream_id: streamId, workspace_id: workspaceId } = event;
  if (!workspaceId || workspaceId !== scope.workspaceId) return;
  const entityId = (field: string, streamKind?: string) =>
    nonEmptyString(payload[field]) ?? (kind === streamKind ? streamId : undefined);
  const project = entityId("project_id", "project");
  const matchesProject = scope.projectId === null || project === undefined || project === scope.projectId;
  const scoped = keys.forScope(scope);
  const name = shortName(event.type);
  const invalidate = (...targets: (QueryKey | undefined)[]) => {
    for (const queryKey of targets) {
      if (queryKey !== undefined) void queryClient.invalidateQueries({ queryKey });
    }
  };
  const invalidateAutopilot = (projectId: string) =>
    invalidate(keys.forScope({ workspaceId, projectId }).autopilot(projectId));

  switch (name) {
    case "ProjectCreated":
    case "ProjectArchived":
      invalidate([...keys.workspace(workspaceId), "projects"]);
      if (name === "ProjectArchived" && project) {
        invalidate([...keys.scope({ workspaceId, projectId: project }), "project-detail"]);
      }
      return;
    case "FileAdded":
    case "FileVersionAdded":
    case "FileTrashed":
    case "FileRestored": {
      invalidate([...keys.workspace(workspaceId), "files"]);
      if (matchesProject) {
        const file = entityId("file_id", "file");
        invalidate(project ? scoped.files(project) : scoped.filesRoot(), file ? scoped.file(file) : undefined);
      }
      return;
    }
    case "ConfigChanged":
    case "ConfigLocked":
    case "ConfigUnlocked": {
      const target = configScope(payload.scope);
      if (!target) return;
      const key = nonEmptyString(payload.key);
      const changed = Array.isArray(payload.keys)
        ? payload.keys.flatMap((value: unknown) => nonEmptyString(value) ?? [])
        : [];
      const history = new Set(key ? [key, ...changed] : changed);
      const workspaceConfig = target === `workspace:${workspaceId}`;
      const projectConfig = target.startsWith("project:");
      if (workspaceConfig || projectConfig) {
        if (history.size === 0 || history.has(attemptLiveSetting)) {
          void queryClient.invalidateQueries({
            queryKey: keys.workspace(workspaceId),
            predicate: ({ queryKey }) => queryKey.at(-1) === attemptLiveSetting && queryKey.at(-3) === "config"
              && (workspaceConfig || queryKey.at(-2) === target),
          });
        }
        if (name === "ConfigChanged" && (history.size === 0 || [...history].some(key => key.startsWith("execution.autopilot.")))) {
          const affectedProject = projectConfig ? target.slice("project:".length) : scope.projectId;
          if (affectedProject) invalidateAutopilot(affectedProject);
        }
      }
      if (projectConfig && scope.projectId !== null && target !== `project:${scope.projectId}`) return;
      invalidate(scoped.configExplain(target), ...(history.size
        ? [...history].map((key) => scoped.configHistory(target, key))
        : [scoped.configHistory(target)]));
      return;
    }
  }

  if (!matchesProject) return;
  if (project && (/^Run[A-Z]/u.test(name) || name === "AutopilotStateChanged")) invalidateAutopilot(project);
  const plan = entityId("plan_id", "plan");
  const draft = entityId("draft_id");
  const planList = project ? scoped.plans(project) : scoped.plansRoot();
  const run = entityId("run_id", "run");
  const task = entityId("task_id");
  const attempt = entityId("attempt_id");
  const runDetail = run ? scoped.run(run) : undefined;
  const reviewRoi = run ? scoped.reviewRoi(run) : undefined;
  const taskDetail = task ? scoped.task(task) : undefined;
  const draftRoot = scoped.draftsRoot();
  const invalidateDraftReads = (draftId: string) => {
    void queryClient.invalidateQueries({
      queryKey: scoped.draft(draftId), predicate: (query) => !isPreview(query, draftRoot),
    });
  };

  switch (/^Task[A-Z]/u.test(name) ? "TaskChanged" : name) {
    case "PlanCreated":
    case "PlanArchived":
    case "PlanRevisionPublished":
      invalidate(planList, plan ? scoped.plan(plan) : undefined);
      if (name === "PlanRevisionPublished" && plan) {
        invalidate(scoped.revisions(plan));
        if (draft) invalidateDraftReads(draft);
        void queryClient.invalidateQueries({
          queryKey: draftRoot, refetchType: "none",
          predicate: (query) => isPreview(query, draftRoot) && query.queryKey[draftRoot.length + 2] === plan,
        });
      }
      break;
    case "DraftOpened":
    case "DraftSaved":
    case "DraftRebased":
    case "DraftAbandoned":
      // The plan key also covers its open-drafts list. The project list contains draft counts.
      if (plan) invalidate(scoped.plan(plan), planList);
      if (!draft) break;
      invalidateDraftReads(draft);
      // The publish dialog must require an explicit refresh and renewed confirmation.
      void queryClient.invalidateQueries({
        queryKey: scoped.draft(draft), predicate: (query) => isPreview(query, draftRoot), refetchType: "none",
      });
      break;
    case "RunCreated":
    case "RunStarted":
    case "RunPaused":
    case "RunResumed":
    case "RunWaiting":
    case "RunFinished":
    case "RunCancelled":
      invalidate(runDetail, project ? scoped.runs(project) : scoped.runsRoot());
      break;
    case "TaskChanged":
    case "AssignmentLeased":
      invalidate(run ? scoped.runTasks(run) : undefined, taskDetail, runDetail);
      break;
    case "LeaseExpired": {
      const affected = task ?? taskForAttempt(queryClient, scoped, attempt);
      invalidate(run ? scoped.runTasks(run) : undefined, affected ? scoped.task(affected) : scoped.tasksRoot(), runDetail);
      break;
    }
    case "AttemptStarted":
    case "StageStarted":
    case "OutputSealed":
    case "CheckCompleted":
      invalidate(attempt ? scoped.attempt(attempt) : undefined, taskDetail);
      break;
    case "StageCompleted":
      invalidate(attempt ? scoped.attempt(attempt) : undefined, taskDetail, reviewRoi);
      break;
    case "StageRecovered":
    case "StepObservationRecorded":
      invalidate(reviewRoi);
      break;
    case "ReviewCompleted": {
      const affected = attempt ?? attemptForReview(queryClient, scoped, task, payload);
      invalidate(affected ? scoped.attempt(affected) : scoped.attemptsRoot(), taskDetail, reviewRoi);
      break;
    }
    case "ManualVerdictRecorded":
      invalidate(scoped.inbox(), runDetail, reviewRoi);
      break;
    case "DecisionRequested":
    case "DecisionAnswered":
    case "DeviationAccepted":
      invalidate(scoped.inbox(), runDetail);
      break;
    case "IntentProposed":
    case "IntentApproved":
    case "IntentDenied":
    case "IntentResolved": {
      const intent = entityId("intent_id", "intent");
      const affected = intent ? runsForIntent(queryClient, scoped, payload, intent) : new Set<string>();
      if (run) affected.add(run);
      invalidate(scoped.inbox(), ...[...affected].map(scoped.run));
      if (!affected.size) {
        const queryKey = scoped.runRoot();
        void queryClient.invalidateQueries({ queryKey, predicate: (query) => query.queryKey[queryKey.length + 1] === "detail" });
      }
      break;
    }
    case "BudgetExhausted":
      invalidate(run ? scoped.runBudget(run) : undefined);
      toast?.({ message: "Бюджет запуска исчерпан", ...(event.request_id ? { requestId: event.request_id } : {}) });
      break;
    case "WorkerStateChanged":
      invalidate(scoped.workers(workspaceId));
      break;
  }
}
