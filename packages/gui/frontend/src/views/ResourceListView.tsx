import type { ResourceList } from "../contracts";
import { StatusBadge, ViewLinkTo, formatScalar } from "./common";

function Cell({ type, value }: { type: string; value: string | number | boolean | null | undefined }) {
  if (type === "status" && typeof value === "string") return <StatusBadge status={value} />;
  if (type === "progress" && typeof value === "number") {
    const percent = Math.round(Math.max(0, Math.min(1, value)) * 100);
    return (
      <span className="progress">
        <progress max={100} value={percent} aria-label={`${percent}%`} /> {percent}%
      </span>
    );
  }
  if (type === "date" && typeof value === "string") return <time dateTime={value}>{value.replace("T", " ").replace("Z", " UTC")}</time>;
  return <>{formatScalar(value)}</>;
}

export function ResourceListView({ data, projectId }: { data: ResourceList; projectId?: string }) {
  return (
    <table className="resource-list">
      <thead>
        <tr>
          {data.columns.map((column) => (
            <th key={column.id} className={column.type === "number" ? "num" : undefined}>
              {column.title}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.rows.map((row) => (
          <tr key={row.id}>
            {data.columns.map((column, index) => (
              <td key={column.id} className={column.type === "number" ? "num" : undefined}>
                {index === 0 ? (
                  <ViewLinkTo link={row.link} projectId={projectId}>
                    <Cell type={column.type} value={row.cells[column.id]} />
                  </ViewLinkTo>
                ) : (
                  <Cell type={column.type} value={row.cells[column.id]} />
                )}
              </td>
            ))}
          </tr>
        ))}
        {data.rows.length === 0 && (
          <tr>
            <td colSpan={data.columns.length} className="muted">
              Nothing to show.
            </td>
          </tr>
        )}
      </tbody>
      {typeof data.total === "number" && data.total > data.rows.length && (
        <tfoot>
          <tr>
            <td colSpan={data.columns.length} className="muted">
              {data.rows.length} of {data.total}
            </td>
          </tr>
        </tfoot>
      )}
    </table>
  );
}
