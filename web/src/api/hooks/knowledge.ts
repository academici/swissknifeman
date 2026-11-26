import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../app/providers/AuthProvider";
import type { WhoAmIView } from "../generated/access";
import type { Uuid } from "../generated/kernel";
import type { DeprecateLesson, LessonView, LessonsView, MemorySearchView, MemoryView, Remember } from "../generated/knowledge";
import { API_ROUTES } from "../generated/openapi";
import { useIdempotentMutation } from "../idempotency";

export function useKnowledgePermissions(scope: string) {
  const { transport } = useAuth();
  return useQuery({
    queryKey: ["access", "me", scope],
    queryFn: async ({ signal }) => (await transport.request<WhoAmIView>(
      "GET", `/api/v1/me?scope_id=${encodeURIComponent(scope)}`, { signal },
    )).data,
  }).data;
}

export function useHandoffPredecessor(project: string, conflictRequestId: string | undefined) {
  const { transport } = useAuth();
  const { method, path } = API_ROUTES.knowledge_list_memory;
  return useQuery({
    queryKey: ["knowledge", "memory", project, "handoff", conflictRequestId],
    enabled: conflictRequestId !== undefined,
    gcTime: 0,
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({ scope: "project", include_expired: "true", limit: "200" });
      const entries = path.replace("{project_id}", encodeURIComponent(project));
      let after: string | null = null;
      do {
        if (after) params.set("after", after);
        const { data } = await transport.request<MemoryView>(method, `${entries}?${params}`, { signal });
        const handoff = data.items.find(entry => entry.kind === "active_handoff" && entry.state === "live");
        if (handoff) return handoff;
        after = data.next_cursor;
      } while (after);
      return null;
    },
  });
}

export function useMemory(project: string, shared: boolean) {
  const { transport } = useAuth();
  const cache = useQueryClient();
  const searchRoute = API_ROUTES.knowledge_search_memory;
  const rememberRoute = API_ROUTES.knowledge_remember;
  const projectId = encodeURIComponent(project);
  const key = ["knowledge", "memory", project];
  const recall = useQuery({
    queryKey: [...key, shared],
    queryFn: async ({ signal }) => (await transport.request<MemorySearchView>(
      searchRoute.method, `${searchRoute.path.replace("{project_id}", projectId)}?include_shared=${shared}`, { signal },
    )).data,
  });
  const remember = useIdempotentMutation(async (input: { body: string; predecessor: Uuid | null }, idempotencyKey) => {
    const body: Omit<Remember, "project_id"> = {
      kind: "active_handoff", source: "api", ttl_hours: null, body: input.body, expected_handoff_id: input.predecessor,
    };
    await transport.request(rememberRoute.method, rememberRoute.path.replace("{project_id}", projectId), { body, idempotencyKey });
    await cache.invalidateQueries({ queryKey: key });
  });
  return { recall, remember };
}

export function useLessons(workspace: string, project: string | null, after: string | null) {
  const { transport } = useAuth();
  const cache = useQueryClient();
  const listRoute = API_ROUTES.knowledge_list_lessons;
  const deprecateRoute = API_ROUTES.knowledge_deprecate_lesson;
  const workspaceId = encodeURIComponent(workspace);
  const key = ["knowledge", "lessons", workspace];
  const params = new URLSearchParams();
  if (project) params.set("project_id", project);
  if (after) params.set("after", after);
  const lessons = useQuery({
    queryKey: [...key, project, after],
    queryFn: async ({ signal }) => (await transport.request<LessonsView>(
      listRoute.method, `${listRoute.path.replace("{workspace_id}", workspaceId)}?${params}`, { signal },
    )).data,
  });
  const deprecate = useIdempotentMutation(async (input: { lesson: LessonView; reason: string }, idempotencyKey) => {
    const path = deprecateRoute.path.replace("{workspace_id}", workspaceId).replace("{lesson_id}", encodeURIComponent(input.lesson.id));
    const body: Pick<DeprecateLesson, "reason"> = { reason: input.reason };
    await transport.request(deprecateRoute.method, path, {
      body, ifMatch: `W/"v${input.lesson.row_version}"`, idempotencyKey,
    });
    await cache.invalidateQueries({ queryKey: key });
  });
  return { lessons, deprecate };
}
