import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import type { ProjectDocument, ProjectList } from "../contracts";
import { navRoutes, routePath, useCatalog } from "../app/catalog";
import { ErrorPanel } from "../app/ErrorView";
import { ApiError } from "../transport/ApiError";
import { useTransport } from "../transport/context";
import { WidgetGrid } from "./Dashboard";

export function useProjects() {
  const transport = useTransport();
  return useQuery({ queryKey: ["projects"], queryFn: () => transport.request<ProjectList>("GET", "/v1/projects") });
}

function AddProject() {
  const transport = useTransport();
  const queryClient = useQueryClient();
  const [path, setPath] = useState("");
  const [confirm, setConfirm] = useState<{ token: string; summary: string } | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function add(token?: string) {
    setError(null);
    try {
      await transport.request<ProjectDocument>("POST", "/v1/projects", { path, ...(token ? { confirm: token } : {}) });
      setConfirm(null);
      setPath("");
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "CONFIRMATION_REQUIRED" && typeof caught.details.confirm === "string") {
        setConfirm({ token: caught.details.confirm, summary: String(caught.details.summary ?? "") });
      } else {
        setError(caught);
      }
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void add();
  }

  return (
    <form className="add-project" onSubmit={submit}>
      <label htmlFor="project-path">Add a project (absolute folder path)</label>
      <input id="project-path" value={path} onChange={(event) => setPath(event.target.value)} placeholder="/home/me/projects/app" />
      <button type="submit" disabled={!path.startsWith("/")}>
        Add
      </button>
      {confirm && (
        <div className="dialog" role="dialog" aria-label="Confirm the project">
          <p>{confirm.summary}</p>
          <button type="button" onClick={() => void add(confirm.token)}>
            Trust this project
          </button>
          <button type="button" onClick={() => setConfirm(null)}>
            Cancel
          </button>
        </div>
      )}
      {error ? <ErrorPanel error={error} /> : null}
    </form>
  );
}

export function Projects() {
  const projects = useProjects();
  return (
    <div>
      <h1>Projects</h1>
      {projects.isError && <ErrorPanel error={projects.error} />}
      <ul className="project-list">
        {projects.data?.projects.map((project) => (
          <li key={project.id}>
            <Link to={`/projects/${project.id}`}>{project.name}</Link> <span className="muted">{project.root}</span>
          </li>
        ))}
        {projects.data && projects.data.projects.length === 0 && <li className="muted">No project yet.</li>}
      </ul>
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
        <nav className="tabs">
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
