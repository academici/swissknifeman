import { Link, useLocation } from "react-router";
import { inboxTarget, useExecutionDetail, useInboxRequests } from "../../api/hooks/execution";
import { allowed, withParams } from "../../api/hooks/workspace";
import { useAuth } from "../providers/AuthProvider";
import { useScope } from "../providers/ScopeProvider";

export function InboxCounter() {
  const { me } = useAuth();
  const { scope } = useScope();
  const { pathname, search } = useLocation();
  const explicit = pathname === "/inbox" ? new URLSearchParams(search).get("scope") : null;
  const target = inboxTarget(explicit, scope.projectId);
  const [level, id = ""] = target?.split(":") ?? [];
  const run = useExecutionDetail("run", level === "run" ? id : "");
  const project = level === "run" ? run.data?.project_id ?? null : id;
  const workspace = level === "run" ? run.data?.workspace_id ?? null : scope.workspaceId;
  const ready = project === scope.projectId && workspace === scope.workspaceId;
  const { query } = useInboxRequests(ready && allowed(me, "inbox.read", id, project, workspace) ? target : null, "all", "open");
  const count = query.data && `${query.data.items.length}${query.data.next_after ? "+" : ""}`;
  return <Link to={withParams("/inbox", { scope: explicit, project_id: project, workspace_id: workspace })}>
    Входящие{count === undefined ? "" : ` (${count})`}
  </Link>;
}
