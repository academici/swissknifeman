import { skipToken, useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { useStream } from "../../app/providers/StreamProvider";
import type { WhoAmIView } from "../generated/access";
import { ApiError } from "../errors";
import type { HostView, ListHostsView, ListWorkersView, ProjectView, RegisterWorker, RegisterWorkerResult, SetWorkerState, SetWorkerStateResult, WorkerView } from "../generated/workspace";
import { newKey, useIdempotentMutation } from "../idempotency";
import { keys } from "../keys";
import type { Transport } from "../transport";

export const api = "/api/v1";
export const segment = encodeURIComponent;
export const workspacesKey = ["workspaces"] as const;
export const versionTag = (version: number) => `W/"v${version}"`;

export function withParams(path: string, params: Record<string, string | null | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  return query.size ? `${path}?${query}` : path;
}

// /me indexes effective grants by scope UUID. Inheritance follows only this resource's ancestry.
export function allowed(me: WhoAmIView | undefined, permission: string, ...ancestors: (string | null)[]) {
  if (!me) return false;
  for (const id of ancestors) {
    if (id && Object.hasOwn(me.permissions_by_scope, id)) return me.permissions_by_scope[id]?.includes(permission) === true;
  }
  const instance = me.memberships.find(membership => membership.scope_kind === "instance");
  const instancePermissions = (instance && me.permissions_by_scope[instance.scope_id]) ?? me.effective_permissions;
  return instancePermissions.includes(permission);
}

function matchesWorkspace(data: unknown, workspaceId: string | null) {
  return !data || typeof data !== "object" || !("workspace_id" in data) || data.workspace_id === workspaceId;
}

export function useRead<T>(key: QueryKey, path: string, enabled = true, poll = false) {
  const { transport } = useAuth();
  const { readWithEvents } = useStream();
  const client = useQueryClient();
  const staleAfterMs = 1000 * (client.getQueryData<number>(["config", "instance", "ui.stale_after_seconds"]) ?? 30);
  const { scope } = useScope();
  return useQuery({
    queryKey: [...key, path], enabled,
    ...(poll && { staleTime: staleAfterMs, refetchInterval: staleAfterMs }),
    queryFn: async ({ signal }) => {
      const read = async () => {
        const response = await transport.request<T>("GET", api + path, { signal });
        // A deep link can resolve a file in a different workspace from the saved
        // selection. Its sequence is meaningful only after the scope changes.
        if (!matchesWorkspace(response.data, scope.workspaceId)) delete response.eventsCursor;
        return response;
      };
      const response = poll ? await read() : await readWithEvents(read, signal);
      return response.data;
    },
  });
}

export function useProject(projectId: string) {
  const { scope } = useScope();
  return useRead<ProjectView>([...keys.scope(scope), "project-detail"], `/projects/${segment(projectId)}`);
}

export function useCursor(path: string) {
  const [page, setPage] = useState<{ path: string; cursors: string[] }>({ path, cursors: [] });
  const cursors = page.path === path ? page.cursors : [];
  // Reset history even when a filter is changed back before advancing another page.
  if (page.path !== path) setPage({ path, cursors: [] });
  const after = cursors.at(-1);
  const query = new URLSearchParams({ limit: "50" });
  if (after) query.set("after", after);
  return {
    path: path + (path.includes("?") ? "&" : "?") + query,
    onNext: (cursor: string) => { if (!cursors.includes(cursor)) setPage({ path, cursors: [...cursors, cursor] }); },
    ...(after ? { onPrevious: () => setPage({ path, cursors: cursors.slice(0, -1) }) } : {}),
  };
}

export function usePage<T>(path: string, key?: QueryKey, poll = false) {
  const { scope } = useScope();
  const cursor = useCursor(path);
  const query = useRead<{ items: readonly T[]; next: string | null }>(
    key ?? keys.scope(scope), cursor.path, true, poll,
  );
  return { query, cursor };
}

export interface Command {
  path: string;
  body?: unknown;
  version?: number;
  method?: "POST" | "DELETE";
  signal?: AbortSignal;
}

export function sendCommand<T>(transport: Transport, { path, body, version, method = "POST", signal }: Command, key = newKey()) {
  return transport.request<T>(method, api + path, {
    body, idempotencyKey: key, ...(signal ? { signal } : {}), ...(version === undefined ? {} : { ifMatch: versionTag(version) }),
  });
}

export function useCommand(workspaceId: string | null, onSuccess?: () => void) {
  const { transport } = useAuth();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (command: Command) => sendCommand(transport, command),
    retry: false,
    onSuccess: async () => {
      await Promise.all([keys.workspace(workspaceId), workspacesKey].map(queryKey =>
        client.invalidateQueries({ queryKey })));
      onSuccess?.();
    },
  });
}

// Preserve error codes and request IDs without echoing credentials or host paths.
export function operatorError(error: unknown) {
  if (!(error instanceof ApiError)) return error;
  return new ApiError({
    status: error.status, code: error.code, category: error.category,
    detail: error.status === 0 ? "Сервер недоступен" : `HTTP ${error.status}`,
    details: {}, requestId: error.requestId, instance: "", retryable: error.retryable,
  });
}

export function useInstanceRead<T>(group: string, path: string) {
  const { transport } = useAuth();
  // AuthenticatedShell owns the config read. Observe it even if it arrives after the first poll.
  const { data: seconds } = useQuery<number | null>({
    queryKey: ["config", "instance", "ui.stale_after_seconds"], queryFn: skipToken,
  });
  const interval = (seconds ?? 30) * 1000;
  return useQuery({
    queryKey: ["instance", group, path], staleTime: interval,
    refetchInterval: interval, refetchOnWindowFocus: "always",
    queryFn: async ({ signal }) => {
      try {
        return (await transport.request<T>("GET", api + path, { signal })).data;
      } catch (error) {
        throw operatorError(error);
      }
    },
  });
}

export function useWorkers(workspaceId: string) {
  const { scope } = useScope();
  const cursor = useCursor(`/workspaces/${segment(workspaceId)}/workers`);
  const query = useRead<ListWorkersView>(keys.forScope(scope).workers(), cursor.path);
  return { query: { data: query.data, error: operatorError(query.error) }, cursor };
}

export function useWorkerState() {
  const { transport } = useAuth();
  const { scope } = useScope();
  const client = useQueryClient();
  const workers = keys.forScope(scope).workers();
  return useIdempotentMutation(async ({ worker, state }: { worker: WorkerView; state: SetWorkerState["state"] }, key) => {
    try {
      await sendCommand<SetWorkerStateResult>(transport, {
        path: `/workers/${segment(worker.worker_id)}/state`, version: worker.row_version, body: { state },
      }, key);
    } finally {
      await client.invalidateQueries({ queryKey: workers });
    }
  });
}

export function useHosts(workspaceId: string | null) {
  const cursor = useCursor(withParams("/hosts", { workspace_id: workspaceId }));
  return { query: useInstanceRead<ListHostsView>("hosts", cursor.path), cursor };
}

export function useHost(hostId: string) {
  return useInstanceRead<HostView>("hosts", `/hosts/${segment(hostId)}`);
}

export async function registerWorker(transport: Transport, workspaceId: string, body: Omit<RegisterWorker, "workspace_id">) {
  // Registration forbids idempotency keys. Keep the credential outside both React Query caches.
  const response = await transport.request<RegisterWorkerResult>("POST", `${api}/workspaces/${segment(workspaceId)}/workers`, { body });
  return response.data.token_secret;
}
