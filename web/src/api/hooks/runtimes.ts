import { useScope } from "../../app/providers/ScopeProvider";
import type { ListRuntimesResult, ModelsView, RoleId, RouteExplainView, RuntimeCapabilitiesView } from "../generated/runtimes";
import type { ExplainReport } from "../generated/settings";
import { segment, useInstanceRead, withParams } from "./workspace";

export function useRuntimes(hostId: string) {
  return useInstanceRead<ListRuntimesResult>("runtimes", withParams("/runtimes", { host_id: hostId }));
}

export function useCapabilities(id: string, version: string | null) {
  return useInstanceRead<RuntimeCapabilitiesView>("runtimes", withParams(`/runtimes/${segment(id)}/capabilities`, { runtime_version: version }));
}

export function useModels(id: string, prepareFor?: string) {
  return useInstanceRead<ModelsView>("runtimes", withParams("/runtimes/models", { runtime_id: id, prepare_for: prepareFor }));
}

export function useRuntimeSettings(scope: string, names: readonly string[]) {
  return useInstanceRead<ExplainReport>("runtimes", withParams("/config/effective", { scope, keys: names.join(",") }));
}

export function useRouting(role: RoleId, hostId: string) {
  const { scope: { projectId, workspaceId } } = useScope();
  const scope = projectId ? `project:${projectId}` : workspaceId ? `workspace:${workspaceId}` : "instance";
  return useInstanceRead<RouteExplainView>("runtimes", withParams("/runtimes/routing", { role, scope, host_id: hostId }));
}
