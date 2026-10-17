import { useQuery, type QueryClient } from "@tanstack/react-query";
import type { ActionRequest, PluginHistory, PluginList, Trust } from "../contracts/generated/plugin-api";
import { CATALOG_KEY } from "../app/catalog";
import { useTransport } from "../transport/context";

export const PLUGIN_API = "urn:swissknifeman:gui:plugin-api:v1";

export type PluginDoc = Trust;

const project = (projectId: string | null | undefined) => (projectId ? `?project_id=${encodeURIComponent(projectId)}` : "");
const base = (id: string) => `/v1/plugins/${encodeURIComponent(id)}`;

/** Paths of the plugin endpoints. */
export const paths = {
  list: (projectId?: string | null) => `/v1/plugins${project(projectId)}`,
  detail: (id: string, projectId?: string | null) => `${base(id)}${project(projectId)}`,
  history: (id: string) => `${base(id)}/history?limit=100`,
  action: (id: string, verb: "enable" | "disable" | "release") => `${base(id)}:${verb}`,
  grants: (id: string) => `${base(id)}/grants`,
  revoke: (id: string, grantId: string) => `${base(id)}/grants/${encodeURIComponent(grantId)}:revoke`,
};

/** Query keys: a prefix invalidates every project variant. */
export const keys = {
  list: (projectId?: string | null) => ["plugins", projectId ?? null] as const,
  detail: (id: string, projectId?: string | null) => ["plugin", id, projectId ?? null] as const,
  history: (id: string) => ["plugin-history", id] as const,
};

export function actionBody(confirm?: string): ActionRequest {
  return { $schema: PLUGIN_API, kind: "action_request", ...(confirm ? { confirm } : {}) };
}

export function usePlugins(projectId?: string | null) {
  const transport = useTransport();
  return useQuery({ queryKey: keys.list(projectId), queryFn: () => transport.request<PluginList>("GET", paths.list(projectId)) });
}

export function usePlugin(id: string, projectId?: string | null) {
  const transport = useTransport();
  return useQuery({ queryKey: keys.detail(id, projectId), queryFn: () => transport.request<PluginDoc>("GET", paths.detail(id, projectId)) });
}

export function usePluginHistory(id: string) {
  const transport = useTransport();
  return useQuery({ queryKey: keys.history(id), queryFn: () => transport.request<PluginHistory>("GET", paths.history(id)) });
}

/** After any change of a plugin: the list, the details, the history and the catalog (its routes follow ui_enabled). */
export function invalidatePlugins(queryClient: QueryClient): void {
  for (const queryKey of [["plugins"], ["plugin"], ["plugin-history"], CATALOG_KEY]) {
    void queryClient.invalidateQueries({ queryKey });
  }
}
