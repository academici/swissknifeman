import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import type { InstallPack, PackView, PacksView, ResolutionView, ResourceKind, ResourcesView, ResourceVersionView } from "../generated/extensions";
import { useIdempotentMutation } from "../idempotency";
import { allowed, segment, sendCommand, useCursor, useInstanceRead, withParams, type Command } from "./workspace";

const root = "/extensions";

export function useExtensionAccess() {
  const { me } = useAuth();
  const enabled = me?.modules.extensions !== false;
  const install = enabled && allowed(me, "ext.install");
  const owner = me?.memberships.some(m => m.scope_kind === "instance" && m.role === "owner");
  return { read: enabled && allowed(me, "ext.read"), install, release: install && owner === true };
}

export function usePacks() {
  const cursor = useCursor(root + "/packs");
  return { query: useInstanceRead<PacksView>("extensions", cursor.path), cursor };
}

export function useResources() {
  const cursor = useCursor(root + "/resources?include_quarantined=true");
  return { query: useInstanceRead<ResourcesView>("extensions", cursor.path), cursor };
}

export function usePack(id: string) {
  return useInstanceRead<PackView>("extensions", root + "/packs/" + segment(id));
}

export function useResourceVersion(id: string) {
  return useInstanceRead<ResourceVersionView>("extensions", root + "/resource-versions/" + segment(id) + "?include_bodies=true");
}

export function useResolution(kind: ResourceKind, key: string) {
  const { scope: { projectId, workspaceId } } = useScope();
  const scope = projectId ? `project:${projectId}` : workspaceId ? `workspace:${workspaceId}` : "instance";
  return useInstanceRead<ResolutionView>("extensions", withParams(root + "/resolve", { kind, key, scope }));
}

type ExtensionCommand =
  | { action: "install"; body: InstallPack }
  | { action: "sync" }
  | { action: "delete"; id: string }
  | { action: "quarantine" | "release"; id: string; reason: string };

function extensionRequest(input: ExtensionCommand): Command {
  switch (input.action) {
    case "install": return { path: root + "/packs", body: input.body };
    case "sync": return { path: root + "/packs/sync-builtin" };
    case "delete": return { method: "DELETE", path: root + "/pack-versions/" + segment(input.id) };
    default: return { path: root + "/resource-versions/" + segment(input.id) + "/" + input.action, body: { reason: input.reason } };
  }
}

export function useExtensionCommand() {
  const { transport } = useAuth();
  const client = useQueryClient();
  return useIdempotentMutation(async (input: ExtensionCommand, key) => {
    const { data } = await sendCommand(transport, extensionRequest(input), key);
    await client.invalidateQueries({ queryKey: ["instance", "extensions"] });
    return data;
  });
}
