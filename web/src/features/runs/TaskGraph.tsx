import { useNavigate } from "react-router";
import type { TasksView } from "../../api/generated/execution_10";
import { field, runLink, taskPath } from "../../api/hooks/execution";
import { EmptyState } from "../../components/data/EmptyState";
import { Graph } from "../../components/viz/Graph";

export function TaskGraph({ view, projectId, runId }: { view: TasksView; projectId: string | null; runId: string }) {
  const navigate = useNavigate();
  if (!view.tasks.length) return <EmptyState title="Нет задач" />;
  return <Graph
    nodes={view.tasks.map(task => ({
      id: field(task.task_id), label: field(task.display_key), status: field(task.status),
    }))}
    edges={view.edges.map(edge => ({
      from: field(edge.prerequisite_task_id), to: field(edge.dependent_task_id),
    }))}
    onSelect={id => { void navigate(runLink(taskPath(id), projectId, runId)); }}
  />;
}
