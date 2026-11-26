import type { Key, ReactNode } from "react";
import { EmptyState } from "./EmptyState";

export interface Column<T> {
  readonly id: string;
  readonly header: string;
  cell(row: T): ReactNode;
  readonly align?: "start" | "end";
}

export function Table<T>({ columns, rows, rowKey, empty = "Нет записей" }: {
  columns: readonly Column<T>[];
  rows: readonly T[];
  rowKey(row: T): Key;
  empty?: string;
}) {
  if (rows.length === 0) return <EmptyState title={empty} />;

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map(({ id, header, align }) => <th key={id} scope="col" data-align={align}>{header}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map(({ id, cell, align }) => <td key={id} data-align={align}>{cell(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
