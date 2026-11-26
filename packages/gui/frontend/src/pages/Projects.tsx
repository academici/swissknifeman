import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import type { ProjectDocument, ProjectList } from "../contracts";
import { navRoutes, routePath, useCatalog } from "../app/catalog";
import { ErrorPanel } from "../app/ErrorView";
import { Dialog } from "../components/Dialog";
import { ApiError } from "../transport/ApiError";
import { useTransport } from "../transport/context";
import { WidgetGrid } from "./Dashboard";

export function useProjects() {
  const transport = useTransport();
  return useQuery({ queryKey: ["projects"], queryFn: () => transport.request<ProjectList>("GET", "/v1/projects") });
}

/** Trusting a folder is the one existing action: POST /v1/projects, answered first with a confirmation to accept. */
function useTrust() {
  const transport = useTransport();
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState<{ path: string; token: string; summary: string } | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function trust(path: string, token?: string): Promise<boolean> {
    setError(null);
    try {
      await transport.request<ProjectDocument>("POST", "/v1/projects", { path, ...(token ? { confirm: token } : {}) });
      setConfirm(null);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      return true;
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "CONFIRMATION_REQUIRED" && typeof caught.details.confirm === "string") {
        setConfirm({ path, token: caught.details.confirm, summary: String(caught.details.summary ?? "") });
      } else {
        setError(caught);
      }
      return false;
    }
  }

  const dialog = confirm && (
    <Dialog label="Confirm the project" onEscape={() => setConfirm(null)}>
      <p>{confirm.summary}</p>
      <button type="button" onClick={() => void trust(confirm.path, confirm.token)}>
        Trust this project
      </button>
      <button type="button" onClick={() => setConfirm(null)}>
        Cancel
      </button>
    </Dialog>
  );
  return { trust, dialog, error };
}

function AddProject() {
  const [path, setPath] = useState("");
  const { trust, dialog, error } = useTrust();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await trust(path)) setPath("");
  }

  return (
    <form className="add-project" onSubmit={(event) => void submit(event)}>
      <label htmlFor="project-path">Add a project (absolute folder path)</label>
      <input id="project-path" value={path} onChange={(event) => setPath(event.target.value)} placeholder="/home/me/projects/app" />
      <button type="submit" disabled={!path.startsWith("/")}>
        Add
      </button>
      {dialog}
      {error ? <ErrorPanel error={error} /> : null}
    </form>
  );
}

/** One project of the workspace as the bridge `gui-workspace` lists it (`gui-workspace.projects`). */
export interface WorkspaceProject {
  id: string;
  name: string;
  bound: boolean;
  paths: string[];
  plansStore: string;
}

function cellText(cells: Record<string, unknown>, key: string): string {
  const value = cells[key];
  return typeof value === "string" ? value : "";
}

/** Bound paths from the exact JSON list cell; the display cell is split only when the list is absent and a path is unambiguous. */
function cellPaths(cells: Record<string, unknown>, key: string, display: string): string[] {
  const raw = cells[key];
  let list: unknown;
  try {
    list = typeof raw === "string" ? JSON.parse(raw) : null;
  } catch {
    list = null;
  }
  if (Array.isArray(list)) return list.filter((path): path is string => typeof path === "string" && path.startsWith("/"));
  return display.includes(", /") || !display.includes(", ") ? display.split(", ").filter((path) => path.startsWith("/")) : [];
}

/** The workspace projects, or null when the bridge or the workspace is not there: the page then shows nothing of it. */
export function useWorkspaceProjects() {
  const transport = useTransport();
  return useQuery({
    queryKey: ["workspace-projects"],
    retry: false,
    queryFn: async (): Promise<WorkspaceProject[] | null> => {
      try {
        const data = await transport.request<{ view?: string; rows?: Array<{ id: string; cells?: Record<string, unknown> }> }>(
          "POST", "/v1/queries/gui-workspace.projects", { context: {}, params: {} });
        if (data.view !== "resource-list" || !Array.isArray(data.rows)) return null;
        return data.rows.map((row) => {
          const cells = row.cells ?? {};
          return {
            id: row.id,
            name: cellText(cells, "name") || row.id,
            bound: cellText(cells, "bound") === "yes",
            paths: cellPaths(cells, "paths_json", cellText(cells, "paths")),
            plansStore: cellText(cells, "plans_store"),
          };
        });
      } catch {
        return null;
      }
    },
  });
}

function WorkspaceBinding({ project }: { project: WorkspaceProject }) {
  return (
    <span className="muted" data-testid="workspace-binding">
      {" "}
      · project {project.id} · binding: {project.bound ? "bound here" : "not bound here"} · plans store: {project.plansStore || "-"}
    </span>
  );
}

function UntrustedWorkspaceProjects({ projects }: { projects: WorkspaceProject[] }) {
  const { trust, dialog, error } = useTrust();
  if (projects.length === 0) return null;
  return (
    <section aria-label="Workspace projects not trusted">
      <h2>Workspace projects not trusted yet</h2>
      <ul className="project-list">
        {projects.map((project) => (
          <li key={project.id}>
            {project.name} <span className="muted">{project.id}</span>
            {project.paths.map((path) => (
              <span key={path}>
                {" "}
                <span className="muted">{path}</span>{" "}
                <button type="button" aria-label={`Trust ${project.name} at ${path}`} onClick={() => void trust(path)}>
                  Trust
                </button>
              </span>
            ))}
          </li>
        ))}
      </ul>
      {dialog}
      {error ? <ErrorPanel error={error} /> : null}
    </section>
  );
}

export function Projects() {
  const projects = useProjects();
  const workspace = useWorkspaceProjects();
  const known = workspace.data ?? null;
  const trustedRoots = new Set(projects.data?.projects.map((project) => project.root) ?? []);
  const byRoot = new Map<string, WorkspaceProject>();
  for (const entry of known ?? []) for (const path of entry.paths) byRoot.set(path, entry);
  const untrusted = (known ?? []).filter((entry) => entry.bound && entry.paths.length > 0 && !entry.paths.some((path) => trustedRoots.has(path)));
  return (
    <div>
      <h1>Projects</h1>
      {projects.isError && <ErrorPanel error={projects.error} />}
      <ul className="project-list">
        {projects.data?.projects.map((project) => {
          const entry = byRoot.get(project.root);
          return (
            <li key={project.id}>
              <Link to={`/projects/${project.id}`}>{project.name}</Link> <span className="muted">{project.root}</span>
              {entry && <WorkspaceBinding project={entry} />}
            </li>
          );
        })}
        {projects.data && projects.data.projects.length === 0 && <li className="muted">No project yet.</li>}
      </ul>
      {projects.data && known && <UntrustedWorkspaceProjects projects={untrusted} />}
      <AddProject />
    </div>
  );
}

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const transport = useTransport();
  const catalog = useCatalog();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => transport.request<ProjectDocument>("GET", `/v1/projects/${encodeURIComponent(projectId)}`),
  });
  if (project.isPending) return <div className="muted">Loading the project…</div>;
  if (project.isError) return <ErrorPanel error={project.error} />;
  const routes = navRoutes(catalog.data, "project");
  return (
    <div>
      <h1>{project.data.name}</h1>
      <div className="muted">{project.data.root}</div>
      {routes.length > 0 && (
        <nav className="tabs" aria-label="Project sections">
          {routes.map((route) => {
            const path = routePath(route, {}, project.data.id);
            return path ? (
              <Link key={route.id} to={path}>
                {route.title}
              </Link>
            ) : null;
          })}
        </nav>
      )}
      <WidgetGrid scope="project" projectId={project.data.id} />
    </div>
  );
}
