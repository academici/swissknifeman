import { useScope } from "../../app/providers/ScopeProvider";
import type { ContextDiffView, ContextExplainView, ContextTextView } from "../generated/context";
import { keys } from "../keys";
import { segment, useRead, withParams } from "./workspace";

function manifestPath(projectId: string | null, manifestId: string | undefined) {
  return `/projects/${segment(projectId ?? "")}/context-manifests/${segment(manifestId ?? "")}`;
}

export function useContextManifest(projectId: string | null, manifestId: string | undefined) {
  const { scope } = useScope();
  return useRead<ContextExplainView>(keys.scope(scope), manifestPath(projectId, manifestId), Boolean(projectId && manifestId));
}

export function useContextText(projectId: string, manifestId: string, position?: number) {
  const { scope } = useScope();
  return useRead<ContextTextView>(keys.scope(scope), withParams(manifestPath(projectId, manifestId) + "/text", {
    position: position === undefined ? undefined : String(position),
  }));
}

export function useContextDiff(projectId: string, manifestId: string, baseId: string) {
  const { scope } = useScope();
  return useRead<ContextDiffView>(keys.scope(scope),
    withParams(manifestPath(projectId, manifestId) + "/diff", { base_manifest_id: baseId }));
}
