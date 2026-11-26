import { CreateScopeDialog } from "../workspaces/CreateWorkspaceDialog";

export default function CreateProjectDialog({ workspaceId }: { workspaceId: string }) {
  return <CreateScopeDialog workspaceId={workspaceId} />;
}
