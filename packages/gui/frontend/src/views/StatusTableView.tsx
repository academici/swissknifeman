import type { StatusTable, ViewAction } from "../contracts";
import { StatusBadge } from "./common";

export function StatusTableView({ data, onAction }: { data: StatusTable; onAction?: (action: ViewAction) => void }) {
  return (
    <table className="status-table">
      <tbody>
        {data.rows.map((row) => (
          <tr key={row.id}>
            <td>
              <StatusBadge status={row.status} />
            </td>
            <td>{row.label}</td>
            <td className="detail">{row.detail ?? ""}</td>
            <td>
              {row.repair && onAction && (
                <button type="button" onClick={() => row.repair && onAction(row.repair)}>
                  Repair
                </button>
              )}
            </td>
          </tr>
        ))}
        {data.rows.length === 0 && (
          <tr>
            <td className="muted">Nothing to show.</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
