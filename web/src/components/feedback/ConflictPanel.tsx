import type { ApiError } from "../../api/errors";
import { escapeText } from "../../lib/safeText";
import { JsonView } from "../data/JsonView";

export function ConflictPanel({ error, submitted, current, onReload, onCompare, onRetry }: {
  error: Pick<ApiError, "code" | "detail" | "requestId">;
  submitted: unknown;
  current: unknown;
  onReload(): void;
  onCompare?: () => void;
  onRetry?: () => void;
}) {
  return (
    <section className="error-panel" role="alert">
      <h2>Конфликт изменений</h2>
      <p><code>{escapeText(error.code)}</code>{error.detail !== error.code && <> · {escapeText(error.detail)}</>}</p>
      <p>Запрос <code>{escapeText(error.requestId)}</code></p>
      <h3>Ваша версия</h3>
      <JsonView value={submitted} />
      <h3>Текущая версия</h3>
      <JsonView value={current} />
      <button type="button" onClick={onReload}>Загрузить текущую версию</button>
      {onCompare && <button type="button" onClick={onCompare}>Сравнить версии</button>}
      {onRetry && <button type="button" onClick={onRetry}>Повторить поверх текущей версии</button>}
    </section>
  );
}
