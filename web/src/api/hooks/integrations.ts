import type { DesiredProjectionView, GetHookPolicy, HookDeliveriesView, HookPolicyView, ListHookSubscriptionsResult, ProjectionSummaryView, ProjectionsView } from "../generated/integrations";
import { keys } from "../keys";
import { segment, useCursor, useRead, withParams } from "./workspace";

export function useIntegrations(workspaceId: string, projectId: string, target: GetHookPolicy["target"], selected: ProjectionSummaryView | null) {
  const key = keys.scope({ workspaceId, projectId });
  const project = `/projects/${segment(projectId)}`;
  const workspace = `/workspaces/${segment(workspaceId)}`;
  const projectionsPage = useCursor(project + "/projections");
  const deliveryPage = useCursor(workspace + "/hook-deliveries");
  return {
    projectionsPage, deliveryPage,
    projections: useRead<ProjectionsView>(key, projectionsPage.path),
    subscriptions: useRead<ListHookSubscriptionsResult>(key, withParams(workspace + "/hook-subscriptions", { project_id: projectId })),
    deliveries: useRead<HookDeliveriesView>(key, deliveryPage.path),
    policy: useRead<HookPolicyView>(key, withParams(project + "/integrations/hook-policy", { target })),
    desired: useRead<DesiredProjectionView>(key, withParams(project + "/integrations/desired-projection", {
      target: selected?.target, checkout_binding_id: selected?.checkout_binding_id,
    }), selected !== null),
  };
}
