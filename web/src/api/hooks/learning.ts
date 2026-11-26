import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../app/providers/AuthProvider";
import type { CandidateView, CandidatesView, PromoteCandidate, ReviewCandidate, SignalsView } from "../generated/learning";
import { API_ROUTES } from "../generated/openapi";
import { useIdempotentMutation } from "../idempotency";

type Review = Omit<ReviewCandidate, "workspace_id" | "candidate_id" | "expected_row_version">;
type Promotion = Omit<PromoteCandidate, "workspace_id" | "candidate_id" | "expected_row_version">;

function candidatePath(path: string, workspace: string, candidate?: string) {
  const scoped = path.replace("{workspace_id}", encodeURIComponent(workspace));
  return candidate ? scoped.replace("{candidate_id}", encodeURIComponent(candidate)) : scoped;
}

export function useCandidateList(workspace: string, project: string | null, state: string, after: string | null) {
  const { transport } = useAuth();
  const route = API_ROUTES.learning_list_candidates;
  const params = new URLSearchParams({ states: state });
  if (project) params.set("project_id", project);
  if (after) params.set("after", after);
  return useQuery({
    queryKey: ["learning", workspace, "candidates", project, state, after],
    queryFn: async ({ signal }) => (await transport.request<CandidatesView>(
      route.method, `${candidatePath(route.path, workspace)}?${params}`, { signal },
    )).data,
  });
}

export function useCandidate(workspace: string, id: string, proposalsAfter: string | null, signalsAfter: string | null) {
  const { transport } = useAuth();
  const cache = useQueryClient();
  const key = ["learning", workspace];
  const route = API_ROUTES.learning_get_candidate;
  const signalRoute = API_ROUTES.learning_list_signals;
  const detail = useQuery({
    queryKey: [...key, "candidate", id, proposalsAfter],
    queryFn: async ({ signal }) => {
      const path = candidatePath(route.path, workspace, id);
      const suffix = proposalsAfter ? `?${new URLSearchParams({ proposals_after: proposalsAfter })}` : "";
      return (await transport.request<CandidateView>(route.method, path + suffix, { signal })).data;
    },
  });
  const signals = useQuery({
    queryKey: [...key, "signals", id, signalsAfter],
    queryFn: async ({ signal }) => {
      const path = candidatePath(signalRoute.path, workspace, id);
      const suffix = signalsAfter ? `?${new URLSearchParams({ after: signalsAfter })}` : "";
      return (await transport.request<SignalsView>(signalRoute.method, path + suffix, { signal })).data;
    },
  });
  const review = useIdempotentMutation(async (
    { rowVersion, body }: { rowVersion: number; body: Review }, idempotencyKey,
  ) => {
    const write = API_ROUTES.learning_review_candidate;
    await transport.request(write.method, candidatePath(write.path, workspace, id), {
      body, ifMatch: `W/"v${rowVersion}"`, idempotencyKey,
    });
    await cache.invalidateQueries({ queryKey: key });
  });
  const promote = useIdempotentMutation(async (
    { rowVersion, body }: { rowVersion: number; body: Promotion }, idempotencyKey,
  ) => {
    const write = API_ROUTES.learning_promote_candidate;
    await transport.request(write.method, candidatePath(write.path, workspace, id), {
      body, ifMatch: `W/"v${rowVersion}"`, idempotencyKey,
    });
    await Promise.all([
      cache.invalidateQueries({ queryKey: key }),
      cache.invalidateQueries({ queryKey: ["knowledge", "lessons", workspace] }),
    ]);
  });
  return { detail, signals, review, promote };
}
