import { useParams, useSearchParams } from "react-router";
import { matchRoute, useCatalog } from "../app/catalog";
import { ErrorPanel } from "../app/ErrorView";
import { CommandRunner } from "../components/CommandRunner";
import { QueryView } from "../components/QueryView";
import { Placeholder } from "../views/Placeholder";

/** `/x/<owner>/<path>`: a route of a contribution with its query (context + path params) and its actions. */
export function ContributionRoute() {
  const { owner = "", "*": rest = "" } = useParams();
  const [search] = useSearchParams();
  const projectId = search.get("project") ?? undefined;
  const catalog = useCatalog();
  if (catalog.isPending) return <div className="muted">Loading the catalog…</div>;
  if (catalog.isError) return <ErrorPanel error={catalog.error} />;
  const found = matchRoute(catalog.data, owner, rest);
  if (!found) return <div className="muted">No route {owner}/{rest} in the catalog.</div>;
  const { route, params } = found;
  const needsProject = route.scope !== "fleet";
  return (
    <div>
      <h1>{route.title}</h1>
      {needsProject && !projectId ? (
        <div className="muted">Open this page from a project.</div>
      ) : route.view === "command-form" && route.command ? (
        <CommandRunner commandId={route.command} projectId={projectId} />
      ) : route.query ? (
        <QueryView queryId={route.query} projectId={projectId} params={params} />
      ) : (
        <Placeholder view={`${route.view} (docs)`} />
      )}
      {route.actions && route.actions.length > 0 && (!needsProject || projectId) && (
        <div className="actions">
          {route.actions.map((action) => (
            <details key={action}>
              <summary>{action}</summary>
              <CommandRunner commandId={action} projectId={projectId} />
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
