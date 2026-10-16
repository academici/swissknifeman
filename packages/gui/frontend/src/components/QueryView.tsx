import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ViewAction, ViewData } from "../contracts";
import { ErrorPanel } from "../app/ErrorView";
import { useTransport } from "../transport/context";
import { ViewDataView } from "../views/ViewDataView";
import { CommandRunner } from "./CommandRunner";

/** Runs a query of the catalog with its context and params and shows the answer in its host view. */
export function QueryView({ queryId, projectId, params = {} }: { queryId: string; projectId?: string; params?: Record<string, string> }) {
  const transport = useTransport();
  const context = projectId ? { project_id: projectId } : {};
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
          <CommandRunner commandId={action.command} projectId={projectId} defaults={action.input ?? {}} />
          <button type="button" onClick={() => setAction(null)}>
            Close
          </button>
        </div>
      )}
    </>
  );
}
