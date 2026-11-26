import { useMemo, type ReactNode } from "react";
import { ArrayField } from "./fields/ArrayField";
import { BooleanField } from "./fields/BooleanField";
import { EnumField } from "./fields/EnumField";
import { FieldIssues, type FieldIssue, type FieldProps, type RenderField } from "./fields/FieldFrame";
import { MapField } from "./fields/MapField";
import { NumberField } from "./fields/NumberField";
import { ObjectField } from "./fields/ObjectField";
import { OneOfField } from "./fields/OneOfField";
import { ReadOnlyField } from "./fields/ReadOnlyField";
import { SecretRefField } from "./fields/SecretRefField";
import { StringField } from "./fields/StringField";
import { schemaTouchesSecret, toNode, type SchemaNode, type SchemaRegistry } from "./profile";
import {
  appendPointer, getAtPointer, isRecord, jsonEqual, own, pointerTokens, removeAtPointer, schemaIssues,
  selectedVariant, setAtPointer, type SchemaIssue,
} from "./values";

const emptyRegistry: SchemaRegistry = {};
const noIssues: readonly FieldIssue[] = [];
const maskedIssue: FieldIssue = { code: "SCHEMA_INVALID", message: "Сервер отклонил значение" };

export interface SchemaFormProps {
  schema: unknown;
  registry?: SchemaRegistry;
  value: unknown;
  /** The value is the subtree at this instance pointer. */
  pointer?: string;
  label?: string;
  onChange?: (value: unknown) => void;
  readOnly?: boolean;
  serverError?: unknown;
  issues?: readonly SchemaIssue[];
}

export function SchemaForm({
  schema, registry = emptyRegistry, value, pointer = "", label = "Параметры", onChange,
  readOnly = false, serverError, issues,
}: SchemaFormProps) {
  const node = useMemo(() => toNode(schema, registry, pointer), [schema, registry, pointer]);
  const bound = bindIssues(node, value, pointer, issues ?? schemaIssues(serverError),
    (path) => schemaTouchesSecret(schema, registry, pointerTokens(path.slice(pointer.length)) ?? []));
  const issuesFor = (path: string) => bound.fields.get(path) ?? noIssues;
  const hasIssues = (path: string) => bound.parents.has(path);
  const render: RenderField = (child, location) => {
    const change = (next: unknown) => {
      if (readOnly || !onChange) return;
      const relative = location.pointer.slice(pointer.length);
      const parent = relative.slice(0, relative.lastIndexOf("/"));
      if (next === undefined && relative && !location.retainKey && !Array.isArray(getAtPointer(value, parent))) {
        onChange(removeAtPointer(value, relative));
      } else {
        onChange(setAtPointer(value, relative, next === undefined && relative ? null : next));
      }
    };
    return renderNode(child, {
      ...location, change, render, issuesFor, hasIssues,
      issues: issuesFor(location.pointer), readOnly: readOnly || !onChange,
    });
  };

  return (
    <div className="schema-form">
      <FieldIssues issues={bound.unmapped} />
      {render(node, { pointer, label, value })}
    </div>
  );
}

function renderNode(node: SchemaNode, field: Omit<FieldProps, "node">): ReactNode {
  const key = field.pointer;
  switch (node.kind) {
    case "leaf/string": return <StringField key={key} {...field} node={node} />;
    case "leaf/number": return <NumberField key={key} {...field} node={node} />;
    case "leaf/boolean": return <BooleanField key={key} {...field} node={node} />;
    case "leaf/enum": return <EnumField key={key} {...field} node={node} />;
    case "array/scalar":
    case "array/object": return <ArrayField key={key} {...field} node={node} />;
    case "object": return <ObjectField key={key} {...field} node={node} />;
    case "map": return <MapField key={key} {...field} node={node} />;
    case "oneOf": return <OneOfField key={key} {...field} node={node} />;
    case "secretRef": return <SecretRefField key={key} {...field} node={node} />;
    case "unsupported": return <ReadOnlyField key={key} {...field} node={node} />;
  }
}

function visitFields(
  node: SchemaNode, value: unknown, pointer: string, targets: Map<string, boolean>,
): boolean {
  let sensitive = node.kind === "secretRef" ||
    ((node.kind === "unsupported" || node.kind === "oneOf") && !jsonEqual(value, node.redact(value)));
  const visit = (child: SchemaNode, entry: unknown, key: string | number) => {
    if (visitFields(child, entry, appendPointer(pointer, key), targets)) sensitive = true;
  };
  switch (node.kind) {
    case "object": {
      for (const child of node.properties) {
        visit(child.node, own(value, child.key), child.key);
      }
      if (node.entry && isRecord(value)) {
        const fixed = new Set(node.properties.map(({ key }) => key));
        for (const [key, entry] of Object.entries(value)) {
          if (!fixed.has(key)) visit(node.entry, entry, key);
        }
      }
      break;
    }
    case "array/scalar":
    case "array/object":
      if (Array.isArray(value)) {
        value.forEach((entry: unknown, index) => visit(node.item, entry, index));
      }
      break;
    case "map":
      if (isRecord(value)) {
        for (const [key, entry] of Object.entries(value)) visit(node.entry, entry, key);
      }
      break;
    case "oneOf": {
      const branch = node.variants[selectedVariant(node, value)]?.node;
      if (branch && visitFields(branch, value, pointer, targets)) sensitive = true;
      targets.set(appendPointer(pointer, node.discriminator), false);
      break;
    }
  }
  targets.set(pointer, sensitive);
  return sensitive;
}

function bindIssues(
  node: SchemaNode, value: unknown, pointer: string, issues: readonly SchemaIssue[], touchesSecret: (path: string) => boolean,
) {
  const fields = new Map<string, FieldIssue[]>();
  const parents = new Set<string>();
  const unmapped: FieldIssue[] = [];
  if (!issues.length) return { fields, parents, unmapped };

  const targets = new Map<string, boolean>();
  visitFields(node, value, pointer, targets);
  const sensitiveAt = (path: string) => targets.get(path) || touchesSecret(path);
  for (const issue of issues) {
    if (!pointerTokens(issue.pointer) || (issue.pointer !== pointer && !issue.pointer.startsWith(`${pointer}/`))) {
      unmapped.push(sensitiveAt(pointer) ? maskedIssue : issue);
      continue;
    }

    let path = issue.pointer;
    while (path !== pointer && !targets.has(path)) path = path.slice(0, path.lastIndexOf("/"));
    const issuesAtPath = fields.get(path) ?? [];
    issuesAtPath.push(sensitiveAt(path) ? maskedIssue : issue);
    fields.set(path, issuesAtPath);

    while (!parents.has(path)) {
      parents.add(path);
      if (path === pointer) break;
      path = path.slice(0, path.lastIndexOf("/"));
    }
  }
  return { fields, parents, unmapped };
}
