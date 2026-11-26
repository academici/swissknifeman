import { notifyManager, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef } from "react";
import { useAuth } from "../../app/providers/AuthProvider";
import { ApiError } from "../errors";
import type { WhoAmIView } from "../generated/access";
import type { Uuid } from "../generated/kernel";
import type {
  EntryView, ExplainReport, ExportConfigView, GetHistoryView, GetSchemaView, ImportConfig,
  ImportConfigResult, ListEntriesView, LockValue, LockValueResult, RemoveValue, RemoveValueResult,
  SetValue, SetValueResult, UnlockValue, UnlockValueResult, UnsetValue, UnsetValueResult,
} from "../generated/settings";
import { keys, type QueryScope } from "../keys";
import { readWithEvents } from "../stream";
import type { RequestOptions, Response, Subscription, Transport } from "../transport";

export type SettingsScope = ImportConfig["scope"];
export type SettingsLevel = SettingsScope["level"];
export const settingsLevels = ["instance", "workspace", "project", "plan", "run", "host"] as const;
export const scopeName = ({ level, scope_id }: SettingsScope) => level === "instance" ? level : `${level}:${scope_id}`;
const scopeIdPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/iu;

export function parseSettingsScope(value: string): SettingsScope | undefined {
  if (value === "instance") return { level: "instance" };
  const [name, id, extra] = value.split(":");
  const level = settingsLevels.find((level) => level === name);
  if (level && level !== "instance" && id && extra === undefined && scopeIdPattern.test(id)) {
    return { level, scope_id: id.toLowerCase() as Uuid };
  }
}

const config = "/api/v1/config";
function query(route: string, scope: SettingsScope, params?: Record<string, string>) {
  return `${config}/${route}?${new URLSearchParams({ scope: scopeName(scope), ...params })}`;
}

export function useSettingsSchema(target: SettingsScope) {
  const { transport } = useAuth();
  const { scope } = useSettingsRead();
  return useQuery({
    queryKey: [...keys.scope(scope), "config", scopeName(target), "schema"],
    queryFn: async ({ signal }) => (await transport.request<GetSchemaView>("GET", query("schema", target), { signal })).data,
  });
}

function reportScope(report: ExplainReport, level: "workspace" | "project") {
  return report.chain.find((layer) => layer.level === level)?.scope_id ?? null;
}

export function useSettingsQueryScope(viewed: SettingsScope) {
  const { transport } = useAuth();
  return useQuery({
    queryKey: ["settings-scope", scopeName(viewed)],
    queryFn: async ({ signal }): Promise<QueryScope> => {
      const id = viewed.scope_id ?? null;
      if (viewed.level === "workspace") return { workspaceId: id, projectId: null };
      if (viewed.level === "instance" || viewed.level === "host") return { workspaceId: null, projectId: null };
      const { data } = await transport.request<ExplainReport>(
        "GET", query("explain", viewed, { include_defaults_only: "false" }), { signal },
      );
      return { workspaceId: reportScope(data, "workspace"), projectId: reportScope(data, "project") };
    },
  });
}

type SettingsRead = {
  scope: QueryScope;
  withEvents<T>(read: () => Promise<Response<T>>, signal?: AbortSignal): Promise<Response<T>>;
};

type SettingsFeed = { cursor: number; subscription?: Subscription; stopped: boolean };

export const SettingsReadContext = createContext<SettingsRead | null>(null);

function useSettingsRead() {
  const context = useContext(SettingsReadContext);
  if (!context) throw new Error("SettingsReadContext is missing");
  return context;
}

export function useSettingsStream(scope: QueryScope): SettingsRead {
  const { transport } = useAuth();
  const client = useQueryClient();
  const { workspaceId, projectId } = scope;
  const feed = useRef<SettingsFeed | null>(null);
  useEffect(() => () => {
    feed.current?.subscription?.close();
    feed.current = null;
  }, [workspaceId, projectId, transport]);

  return {
    scope,
    withEvents: (read, signal) => readWithEvents(read, signal, (cursor) => {
      if (workspaceId === null || cursor === undefined) return true;
      if (feed.current && !feed.current.stopped) return feed.current.cursor <= cursor;
      const active: SettingsFeed = { cursor, stopped: false };
      feed.current = active;
      const invalidate = () => notifyManager.schedule(() => {
        if (feed.current === active) {
          // Ancestor edits can change effective values and locks without changing local rows.
          void client.invalidateQueries({ queryKey: [...keys.scope(scope), "config"] });
        }
      });
      active.subscription = transport.events({ workspaceId, after: cursor }, {
        onCursor: (next) => { active.cursor = next; },
        onStopped: () => { active.stopped = true; },
        onEvent: ({ type }) => {
          if (/(^|:)Config(Changed|Locked|Unlocked)(:v\d+)?$/u.test(type)) invalidate();
        },
        onSnapshotRequired: invalidate,
      });
      return true;
    }),
  };
}

export function useSettingsExplain(target: SettingsScope) {
  const { transport } = useAuth();
  const { scope, withEvents } = useSettingsRead();
  return useQuery({
    queryKey: keys.forScope(scope).configExplain(scopeName(target)),
    queryFn: async ({ signal }) => {
      const response = await withEvents(async () => {
        const response = await transport.request<ExplainReport>(
          "GET", query("explain", target), { signal },
        );
        if (scope.workspaceId === reportScope(response.data, "workspace")) return response;
        // Cursor sequences are local to a workspace.
        const { eventsCursor: _cursor, ...unscoped } = response;
        void _cursor;
        return unscoped;
      }, signal);
      return response.data;
    },
    refetchOnMount: "always",
    // Instance/host updates and some changes to inherited values have no matching workspace event.
    refetchInterval: 30_000,
  });
}

export async function exportSettings(transport: Transport, target: SettingsScope, format: ExportConfigView["format"], signal?: AbortSignal) {
  return (await transport.request<ExportConfigView>("GET", query("export", target, { format, portable_only: "false" }),
    signal ? { signal } : {})).data;
}

export interface EntriesSnapshot {
  readonly entries: readonly EntryView[];
  readonly digest: string;
  readonly hasUnexported: boolean;
}

type Read = <T>(path: string, options: RequestOptions) => Promise<Response<T>>;

async function readEntries(
  read: Read, target: SettingsScope, signal: AbortSignal,
): Promise<EntriesSnapshot> {
  // Export supplies the server's digest. List also includes rows for keys absent from the registry.
  const entries: EntryView[] = [];
  let after: string | null = null;
  do {
    const params = after === null ? undefined : { after };
    const response: ListEntriesView = (await read<ListEntriesView>(
      query("entries", target, params), { signal },
    )).data;
    entries.push(...response.items);
    after = response.next;
  } while (after !== null);
  const { data: exported } = await read<ExportConfigView>(query("export", target, {
    format: "json", portable_only: "false",
  }), { signal });
  const rows = new Map(entries.map((entry) => [entry.key, entry]));
  const matching = exported.entries.every((entry) => {
    const row = rows.get(entry.key);
    return row?.entry_id === entry.entry_id && row.row_version === entry.row_version;
  });
  if (!matching) throw new Error("Settings changed while reading");
  return { entries: exported.entries, digest: exported.digest, hasUnexported: rows.size !== exported.entries.length };
}

function useTargetRead(target: SettingsScope) {
  const { transport } = useAuth();
  const { scope, withEvents } = useSettingsRead();
  const client = useQueryClient();
  const queryKeys = keys.forScope(scope);
  const explainKey = queryKeys.configExplain(scopeName(target));
  const read: Read = <T,>(path: string, options: RequestOptions) => {
    const request = () => transport.request<T>("GET", path, options);
    const report = client.getQueryData<ExplainReport>(explainKey);
    return report && scope.workspaceId !== null && scope.workspaceId === reportScope(report, "workspace") ?
      withEvents(request, options.signal) : request();
  };
  return { read, queryKeys, explainKey };
}

export function useSettingsEntries(target: SettingsScope) {
  const { read, explainKey } = useTargetRead(target);
  return useQuery({
    queryKey: [...explainKey, "entries"],
    queryFn: ({ signal }) => readEntries(read, target, signal),
    refetchInterval: 30_000,
  });
}

export function useSettingsHistory(target: SettingsScope, key: string) {
  const { read, queryKeys } = useTargetRead(target);
  return useInfiniteQuery({
    queryKey: queryKeys.configHistory(scopeName(target), key),
    initialPageParam: null as string | null,
    getNextPageParam: (page: GetHistoryView) => page.next,
    queryFn: async ({ signal, pageParam }) => (await read<GetHistoryView>(
      query("history", target, { key, ...(pageParam === null ? {} : { after: pageParam }) }), { signal },
    )).data,
  });
}

export function useRefreshSettings() {
  const client = useQueryClient();
  const { scope } = useSettingsRead();
  return async () => {
    await client.invalidateQueries({ queryKey: [...keys.scope(scope), "config"] });
  };
}

export async function importSettings(transport: Transport, body: ImportConfig, options: { signal?: AbortSignal; idempotencyKey?: string }) {
  return (await transport.request<ImportConfigResult>("POST", `${config}/import`, { body, ...options })).data;
}

type RowCommand = { scope: SettingsScope; key: string; reason: string; confirmed: boolean };
export type RowWrite = RowCommand & (
  | { op: "set" | "append"; value: unknown; version: number | null }
  | { op: "unset"; version: number | null }
  | { op: "remove" | "lock" | "unlock"; version: number }
);

export function writeSetting(transport: Transport, command: RowWrite, idempotencyKey: string) {
  const { scope, key, version, reason, confirmed } = command;
  const path = `${config}/entries/${encodeURIComponent(scopeName(scope))}/${encodeURIComponent(key)}`;
  const options = {
    idempotencyKey,
    ...(version === null ? { ifNoneMatch: "*" as const } : { ifMatch: `W/"v${version}"` }),
  };
  const body = { reason, confirmed };
  switch (command.op) {
    case "set":
    case "append":
      return transport.request<SetValueResult>("PUT", path, {
        ...options, body: { ...body, value: command.value, mode: command.op } satisfies Omit<SetValue, "scope" | "key">,
      });
    case "unset":
      return transport.request<UnsetValueResult>("POST", `${path}/unset`, {
        ...options, body: body satisfies Omit<UnsetValue, "scope" | "key">,
      });
    case "remove":
      return transport.request<RemoveValueResult>("DELETE", path, {
        ...options, body: body satisfies Omit<RemoveValue, "scope" | "key">,
      });
    case "lock":
      return transport.request<LockValueResult>("POST", `${path}/lock`, {
        ...options, body: body satisfies Omit<LockValue, "scope" | "key">,
      });
    case "unlock":
      return transport.request<UnlockValueResult>("POST", `${path}/unlock`, {
        ...options, body: body satisfies Omit<UnlockValue, "scope" | "key">,
      });
  }
}

export function isSettingsConflict(error: unknown) {
  return error instanceof ApiError && error.status === 409 &&
    (error.code === "VERSION_CONFLICT" || error.code === "ALREADY_EXISTS");
}

export function useSettingsPermissions(target: SettingsScope) {
  const { me, transport } = useAuth();
  const { scope_id: id } = target;
  const scoped = me?.permissions_by_scope;
  const known = target.level === "instance"
    ? scoped?.instance ?? me?.effective_permissions
    : id ? scoped?.[id] ?? scoped?.[scopeName(target)] : undefined;
  const fallback = useQuery({
    queryKey: ["access", "settings-permissions", id],
    enabled: me !== undefined && id !== undefined && target.level !== "instance" && known === undefined,
    queryFn: async ({ signal }) => (await transport.request<WhoAmIView>("GET",
      `/api/v1/me?${new URLSearchParams({ scope_id: id ?? "" })}`, { signal })).data.effective_permissions,
  });
  return new Set(known ?? (fallback.isSuccess ? fallback.data : []));
}
