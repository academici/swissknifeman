import { useSettingsHistory, type SettingsScope } from "../../api/hooks/settings";
import { escapeText } from "../../lib/safeText";
import { KeyValue } from "../data/KeyValue";
import { ErrorPanel } from "../feedback/ErrorPanel";
import { Button } from "../primitives/Button";
import { Dialog } from "../primitives/Dialog";
import { Spinner } from "../primitives/Spinner";
import { safeSettingValue, type KeySpec } from "./draft";
import type { SchemaRegistry } from "./profile";
import { SettingValue } from "./ProvenanceBadge";

export function HistoryDrawer({ scope, spec, registry, onClose }: {
  scope: SettingsScope;
  spec: KeySpec;
  registry: SchemaRegistry;
  onClose(): void;
}) {
  const history = useSettingsHistory(scope, spec.key);
  const items = history.data?.pages.flatMap((page) => page.items) ?? [];
  const state = (op: string | null, locked: boolean | null, value: unknown) =>
    op === null ? <>Нет записи</> : <>
      {escapeText(op)}{locked ? " · 🔒" : ""}{" "}
      <SettingValue value={safeSettingValue(spec, registry, value)} />
    </>;

  return (
    <Dialog open title={`История · ${spec.key}`} onClose={onClose}>
      {history.isPending && <Spinner />}
      {history.isError && <ErrorPanel error={history.error}
        onRetry={() => void (history.isFetchNextPageError ? history.fetchNextPage() : history.refetch())} />}
      {history.isSuccess && !items.length && <p>Записей пока нет.</p>}
      <ol>
        {items.map((item) => (
          <li key={item.id}>
            <p><strong>{escapeText(item.change_kind)}</strong> · {escapeText(item.changed_at)}</p>
            <dl>
              <KeyValue label="Было" value={state(item.old_op, item.old_locked, item.old_value)} />
              <KeyValue label="Стало" value={state(item.new_op, item.new_locked, item.new_value)} />
              <KeyValue label="Автор" value={item.actor_id} />
              <KeyValue label="Причина" value={item.reason} />
              <KeyValue label="Поколение" value={item.generation} />
              {item.request_id && <KeyValue label="Запрос" value={item.request_id} />}
            </dl>
          </li>
        ))}
      </ol>
      {history.hasNextPage && <Button disabled={history.isFetching}
        onClick={() => void history.fetchNextPage()}>Загрузить ещё</Button>}
    </Dialog>
  );
}
