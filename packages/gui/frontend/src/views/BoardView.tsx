import type { ViewData } from "../contracts";
import { StatusBadge, ViewLinkTo } from "./common";

type Board = Extract<ViewData, { view: "board" }>;

/** Columns of cards; a card with a link of the catalog leads to its route, every status is also written as text. */
export function BoardView({ data, projectId }: { data: Board; projectId?: string }) {
  return (
    <div className="board">
      {data.columns.map((column) => (
        <section key={column.id} className="board-column" aria-label={`${column.title}, ${column.cards.length}`}>
          <h2>
            {column.title} <span className="muted">({column.cards.length})</span>
          </h2>
          <ul>
            {column.cards.map((card) => (
              <li key={card.id} className="board-card">
                <div className="card-id">
                  <ViewLinkTo link={card.link} projectId={projectId}>
                    {card.id}
                  </ViewLinkTo>{" "}
                  {card.status ? <StatusBadge status={card.status} /> : null}
                </div>
                <div className="card-title">{card.title}</div>
                {card.subtitle ? <div className="muted">{card.subtitle}</div> : null}
              </li>
            ))}
            {column.cards.length === 0 && <li className="muted">No items.</li>}
          </ul>
        </section>
      ))}
      {data.columns.length === 0 && <div className="muted">Nothing to show.</div>}
    </div>
  );
}
