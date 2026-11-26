import { ApiError } from "../../api/errors";
import { escapeText } from "../../lib/safeText";
import { JsonView } from "../data/JsonView";

const headlines = new Map([
  ["unauthenticated", "Требуется вход"],
  ["forbidden", "Нет доступа"],
  ["not_found", "Не найдено"],
  ["conflict", "Конфликт изменений"],
  ["precondition", "Условие запроса не выполнено"],
  ["validation", "Некорректный запрос"],
  ["backend", "Ошибка сервера"],
]);

export function ErrorPanel({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const problem = error instanceof ApiError ? error : null;
  return (
    <section className="error-panel" role="alert">
      <h2>{headlines.get(problem?.category ?? "") ?? "Не удалось выполнить операцию"}</h2>
      {problem && (
        <>
          <p><code>{escapeText(problem.code)}</code> · {escapeText(problem.detail)}</p>
          {Object.keys(problem.details).length > 0 && <JsonView value={problem.details} />}
          <p>Запрос <code>{escapeText(problem.requestId)}</code></p>
        </>
      )}
      {onRetry && <button type="button" onClick={onRetry}>Повторить</button>}
    </section>
  );
}
