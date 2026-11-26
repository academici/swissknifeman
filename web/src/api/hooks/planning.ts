import { useQuery, useMutation, useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { useAuth } from "../../app/providers/AuthProvider";
import { useScope } from "../../app/providers/ScopeProvider";
import { useStream } from "../../app/providers/StreamProvider";
import type { WhoAmIView } from "../generated/access";
import type { ResourcesView, ResolutionView } from "../generated/extensions";
import type { ResearchResultView } from "../generated/context";
import type { ApproveRevision, ApproveRevisionResult, ReadinessReportView, RevisionVisaStatus,
  ValidateForExecution, ValidateForExecutionResult } from "../generated/execution";
import type { Uuid } from "../generated/kernel";
import type * as P from "../generated/planning";
import type { ExplainReport } from "../generated/settings";
import type { ProjectView } from "../generated/workspace";
import { newKey, useIdempotentMutation } from "../idempotency";
import { keys } from "../keys";

export function isUuid(value: string): value is Uuid {
  return /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
}

export const planPath = (id: string) => `/plans/${encodeURIComponent(id)}`;
const api = "/api/v1";
const projectPlans = (id: string) => `${api}/projects/${encodeURIComponent(id)}/plans`;
type Params = Record<string, string | number | boolean | readonly string[] | undefined>;
function search(params: Params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) value.forEach((item: string) => query.append(key, item));
    else if (value !== undefined) query.set(key, String(value));
  }
  return query.size ? `?${query}` : "";
}

function useScopedKeys() {
  return keys.forScope(useScope().scope);
}

function useRead() {
  const { transport } = useAuth();
  const { readWithEvents } = useStream();
  return async <T,>(path: string, signal: AbortSignal) =>
    (await readWithEvents(() => transport.request<T>("GET", path, { signal }), signal)).data;
}

function useGet<T>(queryKey: QueryKey, path: string, enabled = true) {
  const read = useRead();
  return useQuery({ queryKey, enabled, queryFn: ({ signal }) => read<T>(path, signal) });
}

export function usePlanPermissions(level: "plan" | "project", id: string) {
  const { me, transport } = useAuth();
  const known = me?.permissions_by_scope[id] ?? me?.permissions_by_scope[`${level}:${id}`];
  const permissions = useQuery({
    queryKey: ["access", "permissions", id], enabled: !!me && known === undefined && !!id,
    queryFn: async ({ signal }) => (await transport.request<WhoAmIView>("GET",
      `${api}/me${search({ scope_id: id })}`, { signal })).data.effective_permissions,
  });
  return new Set(known ?? permissions.data);
}

export function usePlans(projectId: string, state: P.ListPlans["state"], after?: string) {
  const path = projectPlans(projectId) + search({ purpose: "standard", state, after });
  return useGet<P.PlansView>([...useScopedKeys().plans(projectId), state, after], path, !!projectId);
}

export function usePlanProject(projectId: string) {
  const { scope } = useScope();
  const path = `/projects/${encodeURIComponent(projectId)}`;
  return useGet<ProjectView>([...keys.scope(scope), "project-detail", path], api + path, false);
}

export function usePlan(planId: string, enabled = true) {
  const { scope } = useScope();
  const { transport } = useAuth();
  const { readWithEvents } = useStream();
  const plan = useQuery({
    queryKey: keys.forScope(scope).plan(planId), enabled: enabled && !!planId,
    queryFn: async ({ signal }) => {
      const read = () => transport.request<P.PlanView>("GET", api + planPath(planId), { signal });
      const snapshot = await read();
      const { data } = snapshot;
      // Cursors from different workspaces cannot be compared. Resolve the owner before joining its feed.
      if (data.workspace_id !== scope.workspaceId || data.project_id !== scope.projectId) return data;
      let first = true;
      return (await readWithEvents(() => {
        if (!first) return read();
        first = false;
        return Promise.resolve(snapshot);
      }, signal)).data;
    },
  });
  const [params, setParams] = useSearchParams();
  const workspace = plan.data?.workspace_id;
  const project = plan.data?.project_id;
  // A direct plan URL may have no saved scope. Re-read under the owning stream.
  useEffect(() => {
    if (!enabled || !workspace || !project || (workspace === scope.workspaceId && project === scope.projectId)) return;
    const next = new URLSearchParams(params);
    next.set("workspace_id", workspace);
    next.set("project_id", project);
    setParams(next, { replace: true });
  }, [enabled, params, setParams, workspace, project, scope.workspaceId, scope.projectId]);
  return plan;
}

export function useResolvePlan(projectId: string, ref: string, followSupersedes = false) {
  return useGet<P.PlanRefView>([...useScopedKeys().plans(projectId), "resolve", ref, followSupersedes],
    api + "/plans/resolve" + search({ project_id: projectId, ref, follow_supersedes: followSupersedes }), !!ref);
}

export function useRevisions(planId: string, before?: string) {
  return useGet<P.RevisionsView>([...useScopedKeys().revisions(planId), before],
    api + planPath(planId) + "/revisions" + search({ before }));
}

export function useDrafts(planId: string) {
  return useGet<P.ListDraftsResult>([...useScopedKeys().plan(planId), "drafts"], api + planPath(planId) + "/drafts?state=open");
}

const draftPath = (planId: string, draftId: string) =>
  api + planPath(planId) + "/drafts/" + encodeURIComponent(draftId);

export function useDraft(planId: string, draftId: string, enabled = true) {
  const { transport } = useAuth();
  const { readWithEvents } = useStream();
  return useQuery({
    queryKey: [...useScopedKeys().draft(draftId), planId], enabled,
    queryFn: ({ signal }) => readWithEvents(() =>
      transport.request<P.DraftView>("GET", draftPath(planId, draftId), { signal }), signal),
  });
}

const draftSavedEvent = "urn:skm:planning:event:draft-saved:v1";

export function useDraftSavedVersion(planId: string, draftId: string, snapshotCursor: number | undefined) {
  const { transport } = useAuth();
  const { scope: { workspaceId } } = useScope();
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (!workspaceId || snapshotCursor === undefined) return;
    const feed = transport.events({
      workspaceId, after: snapshotCursor, streams: [`plan:${planId}`], types: [draftSavedEvent],
    }, {
      onEvent: ({ type, stream_kind, stream_id, payload }) => {
        if (type !== draftSavedEvent || stream_kind !== "plan" || stream_id !== planId || payload.draft_id !== draftId) return;
        const announced = payload.edit_version;
        if (typeof announced === "number" && Number.isSafeInteger(announced)) {
          setVersion((previous) => Math.max(previous, announced));
        }
      },
    });
    return () => feed.close();
  }, [transport, workspaceId, planId, draftId, snapshotCursor]);
  return version;
}

export type PlanSource = { revisionId: string } | { draftId: string; expectedEditVersion: number };
function useSourceKey(planId: string, source: PlanSource) {
  const { scope } = useScope();
  if ("draftId" in source) {
    return [...keys.forScope(scope).draft(source.draftId), planId, "draft", source.draftId, source.expectedEditVersion];
  }
  return [...keys.scope(scope), planId, "revision", source.revisionId];
}

function sourceUrl(planId: string, source: PlanSource, route: string, params: Params, flat = false) {
  const base = api + planPath(planId);
  if ("draftId" in source) {
    const pin = { expected_edit_version: source.expectedEditVersion };
    return flat ? base + route + search({ ...params, ...pin, draft_id: source.draftId })
      : base + "/drafts/" + encodeURIComponent(source.draftId) + route + search({ ...params, ...pin });
  }
  return flat ? base + route + search({ ...params, revision_id: source.revisionId })
    : base + "/revisions/" + encodeURIComponent(source.revisionId) + route + search(params);
}

function useSourceGet<T>(planId: string, source: PlanSource, route: string, params: Params = {}, enabled = true, flat = false) {
  return useGet<T>([...useSourceKey(planId, source), route, params],
    sourceUrl(planId, source, route, params, flat), enabled);
}

export function useRevision(planId: string, revisionId: string) {
  return useSourceGet<P.RevisionView>(planId, { revisionId }, "", { include: "tree" }, !!revisionId);
}

export function useEntity(planId: string, source: PlanSource, ref: string) {
  return useSourceGet<P.EntityView>(planId, source, "/entities/" + encodeURIComponent(ref), {}, !!ref);
}

export function useEntities(planId: string, source: PlanSource, params: Pick<P.ListEntities, "kinds" | "after" | "limit"> = {}) {
  return useSourceGet<P.EntityPageView>(planId, source, "/entities", params, true, true);
}

export function useTreeOutline(planId: string, revisionId: string) {
  const source = { revisionId };
  const read = useRead();
  return useQuery({
    queryKey: [...useSourceKey(planId, source), "tree-outline"],
    queryFn: async ({ signal }) => {
      const rows: P.EntityPageViewItemsItem[] = [];
      let after: string | undefined;
      do {
        const page: P.EntityPageView = await read(sourceUrl(planId, source, "/entities", { after, limit: 100 }, true), signal);
        rows.push(...page.items);
        after = page.next_cursor ?? undefined;
      } while (after);
      return rows;
    },
  });
}

export function useText(planId: string, source: PlanSource, params: Pick<P.ReadText, "target" | "pointer" | "offset_bytes" | "max_bytes">) {
  return useSourceGet<P.TextFragmentView>(planId, source, "/text", params, true, true);
}

export function useDiff(planId: string, source: PlanSource, against?: string) {
  return useSourceGet<P.SpecDiffView>(planId, source, "/diff", { against });
}

export type PreviewOptions = Pick<P.ReadyPreview, "assume_done" | "assume_granted" | "limit">;
export function useReadyPreview(planId: string, source: PlanSource, options: PreviewOptions = {}) {
  return useSourceGet<P.ReadyPreviewView>(planId, source, "/ready-preview", options);
}

export function useStats(planId: string, source: PlanSource) {
  return useSourceGet<P.PlanStatsView>(planId, source, "/stats");
}

export function useExport(planId: string, source: PlanSource, enabled = true) {
  return useSourceGet<P.SpecificationExportView>(planId, source, "/export", {}, enabled);
}

export function useTemplates(projectId: string) {
  const { transport } = useAuth();
  return useQuery({
    queryKey: [...keys.scope(useScope().scope), "plan-templates", projectId],
    queryFn: async ({ signal }) => {
      const names = new Set<string>();
      let after: string | undefined;
      do {
        const path = api + "/extensions/resources" + search({ kind: "plan_template", scope: `project:${projectId}`, after });
        const page: ResourcesView = (await transport.request<ResourcesView>("GET", path, { signal })).data;
        for (const item of page.items) if (item.kind === "plan_template" && !item.quarantined) names.add(item.key);
        after = page.next_cursor ?? undefined;
      } while (after);
      return [...names];
    },
  });
}

export function useTemplate(projectId: string, key: string) {
  const { transport } = useAuth();
  return useQuery({
    queryKey: [...keys.scope(useScope().scope), "plan-template", projectId, key], enabled: !!key,
    queryFn: async ({ signal }) => {
      const path = api + "/extensions/resolve" + search({ scope: `project:${projectId}`, kind: "plan_template", key });
      const { data } = await transport.request<ResolutionView>("GET", path, { signal });
      const schema = data.chosen?.manifest.inputs_schema;
      if (data.chosen?.kind !== "plan_template" || data.chosen.key !== key || !schema || typeof schema !== "object")
        throw new Error("Схема шаблона недоступна");
      return schema;
    },
  });
}

function usePost<I, O>(
  path: string | ((input: I) => string),
  body: (input: I) => unknown,
  invalidate: (data: O) => QueryKey[],
  { etag, updateCache }: { etag?: (input: I) => string; updateCache?: (client: QueryClient, data: O) => void } = {},
) {
  const { transport } = useAuth();
  const client = useQueryClient();
  type Attempt = { url: string; input: I; key: string };
  const mutation = useMutation({
    retry: false,
    mutationFn: async ({ input, url, key }: Attempt) => (await transport.request<O>("POST", url, {
      body: body(input), idempotencyKey: key, ...(etag ? { ifMatch: etag(input) } : {}),
    })).data,
    onSuccess: (data) => {
      updateCache?.(client, data);
      for (const queryKey of invalidate(data)) void client.invalidateQueries({ queryKey });
    },
  });
  function mutate(input: I, options?: { onSuccess(data: O): void }) {
    const url = typeof path === "string" ? path : path(input);
    const previous = mutation.variables;
    const sameAttempt = mutation.isError && previous?.url === url && JSON.stringify(previous.input) === JSON.stringify(input);
    mutation.mutate(sameAttempt ? previous : { url, input, key: newKey() }, options);
  }
  return { ...mutation, mutate, variables: mutation.variables?.input };
}

export function useCreatePlan(projectId: string) {
  const scoped = useScopedKeys();
  return usePost<Omit<P.CreatePlan, "project_id">, P.CreatePlanResult>(projectPlans(projectId),
    (body) => body, () => [scoped.plans(projectId)]);
}

export function useOpenDraft() {
  const scoped = useScopedKeys();
  return usePost<P.OpenDraft, P.OpenDraftResult>((input) => api + planPath(input.plan_id) + "/drafts",
    ({ base }) => ({ base }), (result) => [scoped.plan(result.plan_id), scoped.plansRoot()]);
}

export function useRestoreRevision(planId: string) {
  const scoped = useScopedKeys();
  return usePost<Required<Omit<P.RestoreRevision, "plan_id">>, P.RestoreRevisionResult>(api + planPath(planId) + "/restore",
    (body) => body, () => [scoped.revisions(planId), scoped.plan(planId), scoped.plansRoot()]);
}

export function useArchivePlan(planId: string) {
  const scoped = useScopedKeys();
  const planKey = scoped.plan(planId);
  // ArchivePlan only accepts the row version on the wire. The reason is required at confirmation.
  return usePost<number, P.ArchivePlanResult>(api + planPath(planId) + "/archive", () => ({}),
    () => [planKey, scoped.plansRoot()], {
      etag: (version) => `W/"v${version}"`,
      updateCache: (client, result) => {
        client.setQueryData<P.PlanView>(planKey, (plan) => plan && {
          ...plan, lifecycle_state: result.lifecycle_state, row_version: result.row_version, open_drafts: 0,
        });
      },
    });
}

export type DraftSave = Pick<P.SaveDraft, "expected_edit_version"> & (
  | { merge_patch: NonNullable<P.SaveDraft["merge_patch"]> }
  | { changes: NonNullable<P.SaveDraft["changes"]> }
);

const draftTag = (version: number) => `W/"v${version}"`;

function invalidateDraft(client: QueryClient, scoped: ReturnType<typeof keys.forScope>, planId: string, draftId: string) {
  const preview = scoped.draftPreview(draftId, planId);
  void client.invalidateQueries({ queryKey: preview, refetchType: "none" });
  for (const queryKey of [scoped.plan(planId), scoped.plansRoot(), scoped.draft(draftId)]) {
    void client.invalidateQueries({
      queryKey,
      predicate: (query) => query.queryKey[preview.length - 2] !== "publication-preview",
    });
  }
}

export function useSaveDraft(planId: string, draftId: string) {
  const { transport } = useAuth();
  const scoped = useScopedKeys();
  const client = useQueryClient();
  const path = draftPath(planId, draftId);
  return useMutation({
    retry: false,
    mutationFn: async (input: DraftSave) => {
      const ifMatch = draftTag(input.expected_edit_version);
      const response = "changes" in input
        ? await transport.request<P.SaveDraftResult>("POST", path + "/changes", { body: { changes: input.changes }, ifMatch })
        : await transport.request<P.SaveDraftResult>("PATCH", path, {
          body: input.merge_patch, ifMatch, contentType: "application/merge-patch+json",
        });
      return response.data;
    },
    onSuccess: () => invalidateDraft(client, scoped, planId, draftId),
  });
}

export function useValidateDraft(planId: string, source: Extract<PlanSource, { draftId: string }>, enabled: boolean) {
  const { transport } = useAuth();
  return useQuery({
    queryKey: [...useSourceKey(planId, source), "validate"], enabled, retry: false,
    queryFn: async ({ signal }) => (await transport.request<P.ValidationReportView>(
      "POST", draftPath(planId, source.draftId) + "/validate",
      { signal, body: { expected_edit_version: source.expectedEditVersion } },
    )).data,
  });
}

export function usePublicationPreview(planId: string, draftId: string, version: number, attempt: string) {
  const { transport } = useAuth();
  const client = useQueryClient();
  const queryKey = [...useScopedKeys().draftPreview(draftId, planId), "draft", draftId, version, attempt];
  const preview = useQuery({
    queryKey, retry: false, staleTime: "static",
    queryFn: async ({ signal }) => (await transport.request<P.PublicationPreviewView>(
      "POST", draftPath(planId, draftId) + "/publication-preview",
      { signal, body: { expected_edit_version: version } },
    )).data,
  });
  const query = client.getQueryCache().find({ queryKey, exact: true });
  const [invalidated, setInvalidated] = useState(false);
  useLayoutEffect(() => {
    if (query?.state.isInvalidated) setInvalidated(true);
    return client.getQueryCache().subscribe((event) => {
      // Latch invalidation even if an in-flight response subsequently clears the cache flag.
      if (event.query === query && event.type === "updated" && event.action.type === "invalidate") setInvalidated(true);
    });
  }, [client, query]);
  return { preview, invalidated };
}

export type DraftRebase = Omit<P.RebaseDraft, "plan_id" | "draft_id">;

export function useRebaseDraft(planId: string, draftId: string) {
  const scoped = useScopedKeys();
  const client = useQueryClient();
  return usePost<DraftRebase, P.RebaseDraftResult>(draftPath(planId, draftId) + "/rebase",
    ({ expected_edit_version: _version, ...body }) => { void _version; return body; }, () => [], {
      etag: (input) => draftTag(input.expected_edit_version),
      updateCache: () => invalidateDraft(client, scoped, planId, draftId),
    });
}

export function useAbandonDraft(planId: string, draftId: string) {
  const scoped = useScopedKeys();
  const client = useQueryClient();
  return usePost<number, P.AbandonDraftResult>(draftPath(planId, draftId) + "/abandon", () => ({}), () => [], {
    etag: draftTag,
    updateCache: () => invalidateDraft(client, scoped, planId, draftId),
  });
}

export function usePublishDraft(planId: string, draftId: string) {
  const { transport } = useAuth();
  const scoped = useScopedKeys();
  const client = useQueryClient();
  return useIdempotentMutation(async ({ expected_edit_version, ...body }: Omit<P.PublishRevision, "plan_id" | "draft_id">, key) => {
    const { data } = await transport.request<P.PublishRevisionResult>("POST", draftPath(planId, draftId) + "/publish", {
      body, ifMatch: draftTag(expected_edit_version), idempotencyKey: key,
    });
    invalidateDraft(client, scoped, planId, draftId);
    void client.invalidateQueries({ queryKey: scoped.revisions(planId) });
    return data;
  });
}

export function useDraftWorkPolicy(planId: string) {
  const scoped = useScopedKeys();
  const scope = `plan:${planId}`;
  return useGet<ExplainReport>([...scoped.configExplain(scope), "work-policy"],
    api + "/config/explain" + search({ scope, section: "execution" }));
}

export function useSimulation(planId: string, source: PlanSource, tokensPerSecond: number | undefined) {
  return useSourceGet<P.SimulationView>(planId, source, "/simulate", { tokens_per_second: tokensPerSecond });
}

export function useDesignPlan(planId: string) {
  return usePost<Omit<P.DesignPlan, "plan_id">, P.DesignPlanResult>(
    api + planPath(planId) + "/design-briefs", body => body, () => [],
  );
}

export function usePlanVisa(planId: string, revisionId: string) {
  return useSourceGet<RevisionVisaStatus>(planId, { revisionId }, "/visa");
}

export function useApprovePlanVisa(planId: string, revisionId: string) {
  const statusKey = useSourceKey(planId, { revisionId });
  return usePost<Omit<ApproveRevision, "plan_id">, ApproveRevisionResult>(
    api + planPath(planId) + "/revision-visas", body => body, () => [[...statusKey, "/visa"]],
    { updateCache: (client, latest_signature) => {
      client.setQueryData<RevisionVisaStatus>([...statusKey, "/visa", {}], { latest_signature });
    } },
  );
}

export function useVisaReadiness(planId: string, revisionId: string) {
  return usePost<Pick<ValidateForExecution, "mode">, ValidateForExecutionResult>(
    sourceUrl(planId, { revisionId }, "/readiness", {}), body => body, () => [],
  );
}

export function useVisaReadinessReport(reportId: string) {
  return useGet<ReadinessReportView>([...useScopedKeys().plansRoot(), "visa-readiness", reportId],
    api + "/readiness-reports/" + encodeURIComponent(reportId), !!reportId);
}

export function usePlanResearchProfile(projectId: string) {
  return useGet<ExplainReport>([...useScopedKeys().plans(projectId), "research-profile"],
    api + "/config/effective" + search({
      scope: `project:${projectId}`,
      keys: [
        "context.research.profile.sources", "context.research.profile.max_documents",
        "context.research.profile.query_max_chars", "context.research.profile.excerpt_max_chars",
        "context.research.profile.allow_deep", "context.research.allow_deep",
        "context.research.max_documents", "context.research.query_max_chars", "context.research.excerpt_max_chars",
      ].join(","),
    }));
}

export function useDesignResearchResult(projectId: string, queryId: string) {
  return useGet<ResearchResultView>([...useScopedKeys().plans(projectId), "research-result", queryId],
    api + "/projects/" + encodeURIComponent(projectId) + "/research-queries/" + encodeURIComponent(queryId),
    !!queryId);
}
