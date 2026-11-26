import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { matchPath, useLocation, useNavigate } from "react-router";
import type { ListWorkspacesView, ProjectView } from "../../api/generated/workspace";
import { readWithEvents } from "../../api/stream";
import type { Transport } from "../../api/transport";

const storageKey = "skm.scope";

export function clearSavedScope(): void {
  sessionStorage.removeItem(storageKey);
}

export interface Scope {
  readonly workspaceId: string | null;
  readonly projectId: string | null;
  readonly workspaceSlug: string | null;
}

const emptyScope: Scope = { workspaceId: null, projectId: null, workspaceSlug: null };

function scopePart(value: unknown): string | null {
  return typeof value === "string" && /^[\w-][\w.-]*$/u.test(value) ? value : null;
}

function savedScope(): Scope {
  try {
    const saved: Partial<Scope> | null = JSON.parse(sessionStorage.getItem(storageKey) ?? "null");
    return {
      workspaceId: scopePart(saved?.workspaceId),
      projectId: scopePart(saved?.projectId),
      workspaceSlug: scopePart(saved?.workspaceSlug),
    };
  } catch {
    return emptyScope;
  }
}

function fromLocation(pathname: string, search: string, saved: Scope): Scope {
  const query = new URLSearchParams(search);
  const workspaceSlug = scopePart(matchPath("/w/:workspaceSlug", pathname)?.params.workspaceSlug);
  const projectId = scopePart(matchPath({ path: "/p/:projectId", end: false }, pathname)?.params.projectId)
    ?? scopePart(query.get("project_id"));
  const workspaceId = scopePart(query.get("workspace_id"));
  const workspaceChanged =
    (workspaceSlug !== null && workspaceSlug !== saved.workspaceSlug) ||
    (workspaceId !== null && workspaceId !== saved.workspaceId);
  const projectChanged = projectId !== null && projectId !== saved.projectId;
  return {
    workspaceId: workspaceId ?? (workspaceChanged || projectChanged ? null : saved.workspaceId),
    projectId: projectId ?? (workspaceChanged ? null : saved.projectId),
    workspaceSlug: workspaceSlug ?? (workspaceChanged || projectChanged ? null : saved.workspaceSlug),
  };
}

interface ScopeContextValue {
  scope: Scope;
  projectCursor: number | null;
  chooseWorkspace(id: string | null): void;
  chooseProject(id: string | null): void;
}

const ScopeContext = createContext<ScopeContextValue | null>(null);

interface WorkspaceResolution {
  workspaceId: string | null;
  projectCursor: number | null;
}

async function resolveWorkspace(transport: Transport, scope: Scope, signal: AbortSignal): Promise<WorkspaceResolution | null> {
  if (scope.projectId !== null) {
    const path = `/api/v1/projects/${encodeURIComponent(scope.projectId)}`;
    const { data, eventsCursor } = await readWithEvents<ProjectView>({ transport, path }, signal);
    return { workspaceId: scopePart(data.workspace_id), projectCursor: eventsCursor ?? null };
  }
  // The workspace list endpoint pages by slug and ID but has no slug filter.
  let after: string | null = null;
  do {
    const path: string = after === null ? "/api/v1/workspaces" : `/api/v1/workspaces?after=${encodeURIComponent(after)}`;
    const response = await readWithEvents<ListWorkspacesView>({ transport, path }, signal);
    const match = response.data.items?.find(({ slug }) => slug === scope.workspaceSlug);
    if (match) return { workspaceId: scopePart(match.workspace_id), projectCursor: null };
    after = response.data.next ?? null;
  } while (after !== null);
  return null;
}

export function ScopeProvider({ children, transport }: PropsWithChildren<{ transport?: Transport }>) {
  const location = useLocation();
  const navigate = useNavigate();
  const [saved, setSaved] = useState(savedScope);
  const requested = fromLocation(location.pathname, location.search, saved);
  const { data: resolvedWorkspace } = useQuery({
    queryKey: ["scope-workspace", requested.projectId, requested.workspaceSlug],
    enabled: transport !== undefined && requested.workspaceId === null &&
      (requested.projectId !== null || requested.workspaceSlug !== null),
    // A project ID or slug must resolve to a workspace before its cursor can be used.
    queryFn: ({ signal }) => transport ? resolveWorkspace(transport, requested, signal) : null,
  });
  const scope = { ...requested, workspaceId: requested.workspaceId ?? resolvedWorkspace?.workspaceId ?? null };
  const { workspaceId, projectId, workspaceSlug } = scope;
  const projectCursor = resolvedWorkspace?.workspaceId === workspaceId ? resolvedWorkspace.projectCursor : null;

  useEffect(() => {
    const next = { workspaceId, projectId, workspaceSlug };
    sessionStorage.setItem(storageKey, JSON.stringify(next));
    setSaved((previous) =>
      previous.workspaceId === workspaceId && previous.workspaceSlug === workspaceSlug && previous.projectId === projectId
        ? previous
        : next,
    );
  }, [workspaceId, projectId, workspaceSlug]);

  function chooseWorkspace(id: string | null) {
    setSaved({ ...emptyScope, workspaceId: scopePart(id) });
    void navigate("/");
  }

  function chooseProject(id: string | null) {
    const nextProject = scopePart(id);
    setSaved({ ...emptyScope, projectId: nextProject });
    void navigate(nextProject === null ? "/" : `/p/${encodeURIComponent(nextProject)}`);
  }

  return (
    <ScopeContext.Provider value={{ scope, projectCursor, chooseWorkspace, chooseProject }}>
      {children}
    </ScopeContext.Provider>
  );
}

export function useScope() {
  const value = useContext(ScopeContext);
  if (!value) throw new Error("ScopeProvider is missing");
  return value;
}
