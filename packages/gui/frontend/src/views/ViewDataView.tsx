import type { ViewAction, ViewData } from "../contracts";
import { CommandRunner } from "../components/CommandRunner";
import { RunLog } from "../components/RunLog";
import { BoardView } from "./BoardView";
import { DependencyGraphView } from "./DependencyGraphView";
import { MarkdownView } from "./MarkdownView";
import { MetricGroupView } from "./MetricGroupView";
import { Placeholder } from "./Placeholder";
import { ResourceDetailView } from "./ResourceDetailView";
import { ResourceListView } from "./ResourceListView";
import { StatusTableView } from "./StatusTableView";
import { TimelineView } from "./TimelineView";

/** One host view per `view` of view-data/v1; the kinds of later versions show a placeholder. */
export function ViewDataView({ data, projectId, onAction }: { data: ViewData; projectId?: string; onAction?: (action: ViewAction) => void }) {
  switch (data.view) {
    case "resource-list":
      return <ResourceListView data={data} projectId={projectId} />;
    case "resource-detail":
      return <ResourceDetailView data={data} onAction={onAction} />;
    case "board":
      return <BoardView data={data} projectId={projectId} />;
    case "dependency-graph":
      return <DependencyGraphView data={data} />;
    case "status-table":
      return <StatusTableView data={data} onAction={onAction} />;
    case "metric-group":
      return <MetricGroupView data={data} projectId={projectId} />;
    case "timeline":
      return <TimelineView data={data} projectId={projectId} />;
    case "markdown":
      return <MarkdownView data={data} />;
    case "log-stream":
      return <RunLog runId={data.run_id} />;
    case "command-form":
      return <CommandRunner commandId={data.command} projectId={projectId} defaults={data.defaults ?? {}} />;
    default:
      return <Placeholder view={data.view} />;
  }
}
