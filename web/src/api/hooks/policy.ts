import { useScope } from "../../app/providers/ScopeProvider";
import type { ApproveIntent, ApproveIntentResult, DenyIntent, DenyIntentResult, IntentApprovalView, IntentsView } from "../generated/policy";
import { keys } from "../keys";
import { useInboxCommand } from "./execution";
import { segment, useCursor, useRead, withParams } from "./workspace";

const intentsPath = "/policy/intents";
const intentPath = (id: string) => `${intentsPath}/${segment(id)}`;

export function useProposedIntents(scopeId: string | null, enabled: boolean) {
  const { scope } = useScope();
  const cursor = useCursor(withParams(intentsPath, { workspace_id: scope.workspaceId, scope_id: scopeId, state: "proposed" }));
  const query = useRead<IntentsView>(keys.forScope(scope).inbox(), cursor.path, enabled && scope.workspaceId !== null);
  return { query, cursor };
}

export function useInboxIntent(intentId: string) {
  const { scope } = useScope();
  return useRead<IntentApprovalView>(keys.forScope(scope).inbox(), withParams(intentPath(intentId), { include_approval_binding: "true" }));
}

export function useResolveIntent(intentId: string) {
  const mutation = useInboxCommand<ApproveIntentResult | DenyIntentResult>("resolve-intent", intentId);
  return {
    ...mutation,
    resolve: (body: ApproveIntent | DenyIntent, runId?: string) => {
      const action = "args_digest" in body ? "approve" : "deny";
      mutation.submit({ path: `${intentPath(body.intent_id)}/${action}`, body, version: body.expected_row_version }, runId);
    },
  };
}
