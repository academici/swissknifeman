import { useAuth } from "../providers/AuthProvider";
import { useScope } from "../providers/ScopeProvider";

export function ScopeSwitcher() {
  const { me } = useAuth();
  const { scope, chooseWorkspace, chooseProject } = useScope();
  const slugOption = scope.workspaceId === null && scope.workspaceSlug !== null ? ":" + scope.workspaceSlug : null;

  function choices(kind: "workspace" | "project", selected: string | null) {
    const ids = new Set<string>();
    if (selected) ids.add(selected);
    for (const membership of me?.memberships ?? []) {
      if (membership.scope_kind === kind) ids.add(membership.scope_id);
    }
    return [...ids].map((id) => <option key={id} value={id}>{id}</option>);
  }

  return (
    <div className="scope-switcher">
      <label>
        Пространство
        <select value={scope.workspaceId ?? slugOption ?? ""} onChange={(event) => chooseWorkspace(event.target.value || null)}>
          <option value="">Все пространства</option>
          {slugOption && <option value={slugOption} disabled>{scope.workspaceSlug}</option>}
          {choices("workspace", scope.workspaceId)}
        </select>
      </label>
      <label>
        Проект
        <select value={scope.projectId ?? ""} onChange={(event) => chooseProject(event.target.value || null)}>
          <option value="">Все проекты</option>
          {choices("project", scope.projectId)}
        </select>
      </label>
    </div>
  );
}
