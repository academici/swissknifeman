export function Pagination({ next, onNext, onPrevious, busy = false }: {
  next: string | null;
  onNext(cursor: string): void;
  onPrevious?: () => void;
  busy?: boolean;
}) {
  return (
    <nav aria-label="Страницы" className="pagination">
      {onPrevious && <button type="button" disabled={busy} onClick={onPrevious}>Назад</button>}
      {next !== null && <button type="button" disabled={busy} onClick={() => onNext(next)}>Далее</button>}
    </nav>
  );
}
