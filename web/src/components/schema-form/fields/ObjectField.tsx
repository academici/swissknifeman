import { Fragment } from "react";
import { escapeText } from "../../../lib/safeText";
import type { ObjectNode, Property } from "../profile";
import { appendPointer, own } from "../values";
import { FieldFrame, type FieldProps } from "./FieldFrame";
import { MapContents } from "./MapField";

export function ObjectContents(field: FieldProps<ObjectNode> & { omit?: string }) {
  const properties = field.node.properties.filter(({ key }) => key !== field.omit);
  function fields(entries: readonly Property[]) {
    const groups = new Map<string, Property[]>();
    for (const entry of entries) {
      const group = entry.node.ui.group;
      if (group) {
        const siblings = groups.get(group) ?? [];
        siblings.push(entry);
        groups.set(group, siblings);
      }
    }
    function render({ key, node, required }: Property) {
      return field.render(node, {
        label: key, pointer: appendPointer(field.pointer, key), value: own(field.value, key), required,
      });
    }
    return entries.map((entry) => {
      const group = entry.node.ui.group;
      if (!group) return <Fragment key={entry.key}>{render(entry)}</Fragment>;
      const siblings = groups.get(group);
      if (siblings?.[0] !== entry) return null;
      return <fieldset key={entry.key}><legend>{escapeText(group)}</legend>{siblings.map(render)}</fieldset>;
    });
  }
  const advanced = properties.filter(({ node }) => node.ui.advanced);
  return (
    <>
      {fields(properties.filter(({ node }) => !node.ui.advanced))}
      {advanced.length > 0 && (
        <details open={advanced.some(({ key }) => field.hasIssues(appendPointer(field.pointer, key))) || undefined}>
          <summary>Advanced</summary>
          {fields(advanced)}
        </details>
      )}
      {field.node.entry && <MapContents {...field} entryNode={field.node.entry} />}
    </>
  );
}

export function ObjectField(field: FieldProps<ObjectNode>) {
  const contents = (
    <FieldFrame field={field} group>
      {() => <ObjectContents {...field} />}
    </FieldFrame>
  );
  if (field.node.widget !== "collapsed") return contents;
  return (
    <details open={field.hasIssues(field.pointer) || undefined}>
      <summary>{escapeText(field.node.title ?? field.label)}</summary>
      {contents}
    </details>
  );
}
