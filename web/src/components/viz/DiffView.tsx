import { escapeText } from "../../lib/safeText";

const titles = { added: "Добавлено", removed: "Удалено", changed: "Изменено", rekeyed: "Переименовано", moved: "Перемещено" };
export type DiffKind = keyof typeof titles;

export function DiffView({ changes }: {
  changes: readonly { id: string; kind: DiffKind; label: string; before?: string; after?: string }[];
}) {
  return (
    <div className="diff">
      {(Object.keys(titles) as DiffKind[]).map((kind) => {
        const group = changes.filter((change) => change.kind === kind);
        if (!group.length) return null;
        return (
          <section key={kind}>
            <h3>{titles[kind]}</h3>
            <ul>
              {group.map((change) => (
                <li key={change.id}>
                  {escapeText(change.label)}
                  {change.before !== undefined && <> <del>{escapeText(change.before)}</del></>}
                  {change.after !== undefined && <> <ins>{escapeText(change.after)}</ins></>}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
