import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { ErrorPanel } from "../app/ErrorView";
import type { ConfigModules as ConfigModulesDocument } from "../forms/types";
import { useTransport } from "../transport/context";

/** `/settings/config`: the modules that have a configuration schema. */
export function ConfigModules() {
  const transport = useTransport();
  const modules = useQuery({ queryKey: ["config"], queryFn: () => transport.request<ConfigModulesDocument>("GET", "/v1/config") });
  return (
    <div>
      <h1>Configuration</h1>
      {modules.isPending && <div className="muted">Loading…</div>}
      {modules.isError && <ErrorPanel error={modules.error} />}
      {modules.data && modules.data.modules.length === 0 && <div className="muted">No module has a configuration schema.</div>}
      <ul className="project-list">
        {modules.data?.modules.map((module) => (
          <li key={module.id}>
            <Link to={`/settings/config/${encodeURIComponent(module.id)}`}>{module.id}</Link>
            {module.title ? <span className="muted"> — {module.title}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
