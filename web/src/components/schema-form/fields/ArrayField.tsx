import type { ArrayNode } from "../profile";
import { appendPointer, initialValue } from "../values";
import { FieldFrame, type FieldProps } from "./FieldFrame";

export function ArrayField(field: FieldProps<ArrayNode>) {
  const { node, pointer, readOnly } = field;
  const items: readonly unknown[] = Array.isArray(field.value) ? field.value : [];

  function move(from: number, to: number) {
    const reordered = [...items];
    [reordered[from], reordered[to]] = [reordered[to], reordered[from]];
    field.change(reordered);
  }

  function renderItem(value: unknown, index: number) {
    return field.render(node.item, {
      value, pointer: appendPointer(pointer, index), label: `Элемент ${index + 1}`,
    });
  }

  function actions(index: number) {
    return (
      <>
        <button type="button" disabled={index === 0} aria-label={`Поднять элемент ${index + 1}`}
          onClick={() => move(index, index - 1)}>↑</button>
        <button type="button" disabled={index === items.length - 1} aria-label={`Опустить элемент ${index + 1}`}
          onClick={() => move(index, index + 1)}>↓</button>
        <button type="button" aria-label={`Удалить элемент ${index + 1}`}
          onClick={() => field.change(items.filter((_, itemIndex) => index !== itemIndex))}>Удалить</button>
      </>
    );
  }

  const List = node.widget === "tags" ? "ul" : "ol";
  return (
    <FieldFrame field={field} group>
      {() => (
        <>
          {!readOnly && node.item.kind !== "unsupported" && (
            <button type="button" onClick={() => field.change([...items, initialValue(node.item) ?? null])}>
              Добавить элемент
            </button>
          )}
          {node.widget === "table" ? (
            <table>
              <thead><tr><th scope="col">Элемент</th>{!readOnly && <th scope="col">Действия</th>}</tr></thead>
              <tbody>{items.map((value, index) => (
                <tr key={index}>
                  <td>{renderItem(value, index)}</td>
                  {!readOnly && <td>{actions(index)}</td>}
                </tr>
              ))}</tbody>
            </table>
          ) : (
            <List>{items.map((value, index) => (
              <li key={index}>
                {renderItem(value, index)}
                {!readOnly && <div>{actions(index)}</div>}
              </li>
            ))}</List>
          )}
        </>
      )}
    </FieldFrame>
  );
}
