import { useCatalog } from "../app/catalog";
import { ErrorPanel } from "../app/ErrorView";

export function CatalogPage() {
  const catalog = useCatalog();
  if (catalog.isPending) return <div className="muted">Loading the catalog…</div>;
  if (catalog.isError) return <ErrorPanel error={catalog.error} />;
  const { contributions, rejected, digest } = catalog.data;
  return (
    <div>
      <h1>Catalog</h1>
      <div className="muted">digest {digest}</div>
      <h2>Accepted</h2>
      <table className="resource-list">
        <thead>
          <tr>
            <th>Owner</th>
            <th>Source</th>
            <th className="num">Routes</th>
            <th className="num">Widgets</th>
            <th className="num">Queries</th>
            <th className="num">Commands</th>
          </tr>
        </thead>
        <tbody>
          {contributions.map((entry) => (
            <tr key={`${entry.owner}/${entry.source}`}>
              <td>{entry.owner}</td>
              <td>{entry.source}</td>
              <td className="num">{entry.document.routes?.length ?? 0}</td>
              <td className="num">{entry.document.widgets?.length ?? 0}</td>
              <td className="num">{entry.document.queries?.length ?? 0}</td>
              <td className="num">{entry.document.commands?.length ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Rejected</h2>
      {rejected.length === 0 ? (
        <div className="muted">None.</div>
      ) : (
        <table className="resource-list">
          <thead>
            <tr>
              <th>Code</th>
              <th>Owner</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {rejected.map((entry, index) => (
              <tr key={`${entry.file}-${index}`}>
                <td>
                  <code>{entry.code}</code>
                </td>
                <td>{entry.owner ?? "—"}</td>
                <td>{entry.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
