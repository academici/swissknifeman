import { useId, useState } from "react";
import { escapeText } from "../../../lib/safeText";
import type { MapNode, SchemaNode } from "../profile";
import { appendPointer, initialValue, isRecord, matchesPattern, own, removeAtPointer, setAtPointer } from "../values";
import { FieldFrame, type FieldProps } from "./FieldFrame";

export function MapField(field: FieldProps<MapNode>) {
  return (
    <FieldFrame field={field} group>
      {() => <MapContents {...field} entryNode={field.node.entry} />}
    </FieldFrame>
  );
}

export function MapContents(field: FieldProps & { entryNode: SchemaNode }) {
  const { value, node, pointer, readOnly, entryNode } = field;
  const entries = isRecord(value) ? value : {};
  const fixed = new Set(node.kind === "object" ? node.properties.map(({ key }) => key) : []);
  const pattern = own(node.schema.propertyNames, "pattern");
  const id = useId();
  const [key, setKey] = useState("");
  const [unsafe, setUnsafe] = useState(false);
  const duplicate = fixed.has(key) || Object.hasOwn(entries, key);
  const problem = unsafe ? "Ключ содержит управляющие символы" : duplicate ? "Ключ уже существует" :
    !matchesPattern(key, pattern) ? "Ключ не соответствует шаблону" : undefined;
  const title = node.title ?? field.label;

  return (
    <>
      {!readOnly && (
        <div>
          <label htmlFor={id}>Новый ключ ({escapeText(title)})</label>
          <input id={id} type="text" value={key} aria-describedby={problem ? `${id}-hint` : undefined}
            onChange={(event) => {
              const next = event.currentTarget.value;
              const clean = escapeText(next) === next;
              setUnsafe(!clean);
              if (clean) setKey(next);
            }} />
          <button type="button" onClick={() => {
            if (duplicate || unsafe) return;
            field.change(setAtPointer(entries, appendPointer("", key), initialValue(entryNode) ?? null));
            setKey("");
          }}>Добавить запись</button>
          {problem && <p id={`${id}-hint`}>{problem}</p>}
        </div>
      )}
      {Object.entries(entries).filter(([name]) => !fixed.has(name)).map(([name, entry]) => (
        <fieldset key={name}>
          <legend>{escapeText(name) || '""'}</legend>
          {field.render(entryNode, {
            value: entry, pointer: appendPointer(pointer, name), label: name || '""', retainKey: true,
          })}
          {!matchesPattern(name, pattern) && <p>Ключ не соответствует шаблону</p>}
          {!readOnly && (
            <button type="button" aria-label={`Удалить запись ${escapeText(name)}`}
              onClick={() => field.change(removeAtPointer(entries, appendPointer("", name)))}>Удалить</button>
          )}
        </fieldset>
      ))}
    </>
  );
}
