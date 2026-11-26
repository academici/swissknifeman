export interface QueryScope {
  readonly workspaceId: string | null;
  readonly projectId: string | null;
}

function workspace(workspaceId: string | null) {
  return ["workspace", workspaceId] as const;
}

function scope({ workspaceId, projectId }: QueryScope) {
  return [...workspace(workspaceId), "project", projectId] as const;
}

function forScope(queryScope: QueryScope) {
  const root = scope(queryScope);
  const plansRoot = () => [...root, "plans"] as const;
  const runsRoot = () => [...root, "runs"] as const;
  const runRoot = () => [...root, "run"] as const;
  const tasksRoot = () => [...root, "task"] as const;
  const attemptsRoot = () => [...root, "attempt"] as const;
  const filesRoot = () => [...root, "files"] as const;
  const draftsRoot = () => [...root, "draft"] as const;
  const draft = (draftId: string) => [...draftsRoot(), draftId] as const;
  const draftPreview = (draftId: string, planId: string) =>
    [...draft(draftId), "publication-preview", planId] as const;

  return {
    plansRoot,
    plans: (projectId: string) => [...plansRoot(), projectId] as const,
    plan: (planId: string) => [...root, "plan", planId, "detail"] as const,
    revisions: (planId: string) => [...root, "plan", planId, "revisions"] as const,
    draftsRoot,
    draft,
    draftPreview,
    runsRoot,
    runs: (projectId: string) => [...runsRoot(), projectId] as const,
    runRoot,
    run: (runId: string) => [...runRoot(), runId, "detail"] as const,
    runTasks: (runId: string) => [...runRoot(), runId, "tasks"] as const,
    runBudget: (runId: string) => [...runRoot(), runId, "budget"] as const,
    reviewRoi: (runId: string) => [...runRoot(), runId, "analytics", "review-roi"] as const,
    tasksRoot,
    task: (taskId: string) => [...tasksRoot(), taskId] as const,
    attemptsRoot,
    attempt: (attemptId: string) => [...attemptsRoot(), attemptId] as const,
    inbox: () => [...root, "inbox"] as const,
    configExplain: (configScope: string) => [...root, "config", configScope, "explain"] as const,
    configHistory: (configScope: string, key?: string) =>
      key === undefined
        ? [...root, "config", configScope, "history"] as const
        : [...root, "config", configScope, "history", key] as const,
    filesRoot,
    files: (projectId: string) => [...filesRoot(), projectId] as const,
    file: (fileId: string) => [...root, "file", fileId] as const,
    workers: (workspaceId = queryScope.workspaceId) => [...root, "workers", workspaceId] as const,
    autopilot: (projectId: string) => [...root, "autopilot", projectId] as const,
  };
}

export const keys = { workspace, scope, forScope };
