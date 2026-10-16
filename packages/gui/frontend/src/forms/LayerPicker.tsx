import type { ProjectEntry } from "../contracts";
import type { LayerName } from "./types";

/** The layer to write (machine or project) and the project for the project layer; env, invocation and flags are read-only. */
export function LayerPicker({
  layer,
  onLayer,
  projectId,
  onProject,
  projects,
}: {
  layer: LayerName;
  onLayer: (layer: LayerName) => void;
  projectId: string | null;
  onProject: (projectId: string | null) => void;
  projects: ProjectEntry[];
}) {
  return (
    <div className="layer-picker">
      <label>
        Layer{" "}
        <select aria-label="Layer" value={layer} onChange={(event) => onLayer(event.target.value as LayerName)}>
          <option value="machine">machine</option>
          <option value="project" disabled={!projectId}>
            project{projectId ? "" : " (choose a project)"}
          </option>
        </select>
      </label>
      <label>
        Project{" "}
        <select aria-label="Project" value={projectId ?? ""} onChange={(event) => onProject(event.target.value || null)}>
          <option value="">none</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </label>
      <span className="muted">env, invocation and flags are read-only</span>
    </div>
  );
}
