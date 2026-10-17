import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ViewAction, ViewData } from "../contracts";
import { ErrorPanel } from "../app/ErrorView";
import { useTransport } from "../transport/context";
import { ViewDataView } from "../views/ViewDataView";
import { CommandRunner } from "./CommandRunner";

const CONTEXT_PARAMS = ["plan_id", "item_id", "run_id"] as const;

/** The context of a page: the project plus the plan, item and run ids of the path. The host reads these ids from
 * `context`, never from `params`; the path params stay in `params` too, because the query declares them. */
export function routeContext(projectId: string | undefined, params: Record<string, string> = {}): Record<string, string> {
  const context: Record<string, string> = projectId ? { project_id: projectId } : {};
  for (const key of CONTEXT_PARAMS) {
    const value = params[key];
    if (value) context[key] = value;
  }
  return context;
}

/** Runs a query of the catalog with its context and params and shows the answer in its host view. */
export function QueryView({ queryId, projectId, params = {} }: { queryId: string; projectId?: string; params?: Record<string, string> }) {
  const transport = useTransport();
  const context = routeContext(projectId, params);
  const [action, setAction] = useState<ViewAction | null>(null);
  const query = useQuery({
    queryKey: ["query", queryId, context, params],
    queryFn: () => transport.request<ViewData>("POST", `/v1/queries/${encodeURIComponent(queryId)}`, { context, params }),
  });
  if (query.isPending) return <div className="muted">Loading…</div>;
  if (query.isError) return <ErrorPanel error={query.error} />;
  return (
    <>
      <ViewDataView data={query.data} projectId={projectId} onAction={setAction} />
      {action && (
        <div className="action-panel">
          <CommandRunner commandId={action.command} projectId={projectId} context={context} defaults={action.input ?? {}} />
          <button type="button" onClick={() => setAction(null)}>
            Close
          </button>
        </div>
      )}
    </>
  );
}
