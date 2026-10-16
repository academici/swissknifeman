import { useCatalog, widgetsOf } from "../app/catalog";
import { ErrorPanel } from "../app/ErrorView";
import { QueryView } from "../components/QueryView";

export function WidgetGrid({ scope, projectId }: { scope: "fleet" | "project"; projectId?: string }) {
  const catalog = useCatalog();
  if (catalog.isPending) return <div className="muted">Loading the catalog…</div>;
  if (catalog.isError) return <ErrorPanel error={catalog.error} />;
  const widgets = widgetsOf(catalog.data, scope);
  if (widgets.length === 0) return <div className="muted">No contribution offers a {scope} widget.</div>;
  return (
    <div className="widget-grid">
      {widgets.map((widget) => (
        <section key={`${widget.owner}/${widget.id}`} className={`widget widget-${widget.size ?? "medium"}`}>
          <h2>{widget.title}</h2>
          <QueryView queryId={widget.query} projectId={projectId} />
        </section>
      ))}
    </div>
  );
}

export function Dashboard() {
  return (
    <div>
      <h1>Fleet</h1>
      <WidgetGrid scope="fleet" />
    </div>
  );
}
