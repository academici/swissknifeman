import { useState, type ReactNode } from "react";
import { escapeText } from "../../lib/safeText";
import { Button } from "../primitives/Button";
import { Dialog } from "../primitives/Dialog";
import { Table } from "../data/Table";
import { SettingValue } from "./ProvenanceBadge";
import type { ConflictRow, RowState } from "./draft";

export function ConflictView({ rows, safeValue, disabled, error, actions, onClose, onRebase }: {
  rows: readonly ConflictRow[];
  safeValue(key: string, value: unknown): unknown;
  disabled?: boolean;
  error?: string;
  actions?: ReactNode;
  onClose(): void;
  onRebase(takeCurrent: ReadonlySet<string>): void;
}) {
  const [choices, setChoices] = useState<ReadonlyMap<string, "mine" | "current">>(new Map());
  const required = rows.filter(({ status }) => status === "conflict");
  const render = (key: string, row: RowState | null) => row ? <>
    {escapeText(row.op)}{row.locked ? " · 🔒" : ""}
    {row.row_version !== undefined && ` · v${row.row_version}`}
    {" "}<SettingValue value={safeValue(key, row.value)} />
  </> : <>Нет записи</>;
  const choose = (key: string, choice: "mine" | "current") =>
    setChoices((previous) => new Map(previous).set(key, choice));

  return (
    <Dialog open title="Конфликт изменений" onClose={onClose}>
      <p>Настройки изменились в другой сессии. Выберите версию конфликтующих записей.</p>
      <Table rows={rows} rowKey={(row) => row.key} columns={[
        { id: "key", header: "Ключ", cell: ({ key }) => <code>{escapeText(key)}</code> },
        { id: "base", header: "Base", cell: ({ key, base }) => render(key, base) },
        { id: "current", header: "Current", cell: ({ key, current }) => render(key, current) },
        { id: "yours", header: "Yours", cell: ({ key, yours }) => render(key, yours) },
        { id: "resolution", header: "Решение", cell: ({ key, status }) => status === "conflict" ? (
          <>
            <Button aria-label={escapeText(`Take mine · ${key}`)} aria-pressed={choices.get(key) === "mine"}
              onClick={() => choose(key, "mine")}>Take mine</Button>{" "}
            <Button aria-label={escapeText(`Take current · ${key}`)} aria-pressed={choices.get(key) === "current"}
              onClick={() => choose(key, "current")}>Take current</Button>
          </>
        ) : status },
      ]} />
      {error && <p role="alert">{error}</p>}
      <Button disabled={disabled || required.some(({ key }) => !choices.has(key))} onClick={() => {
        onRebase(new Set([...choices].filter(([, choice]) => choice === "current").map(([key]) => key)));
      }}>Rebase draft</Button>
      {actions}
    </Dialog>
  );
}
