import { useId, type ReactNode } from "react";
import { sanitizeLink } from "../../../lib/safeLink";
import { escapeText } from "../../../lib/safeText";
import type { SchemaNode } from "../profile";
import { advisoryHints, type SchemaIssue } from "../values";

interface FieldLocation {
  pointer: string;
  value: unknown;
  label: string;
  required?: boolean;
  retainKey?: boolean;
}

export type RenderField = (node: SchemaNode, location: FieldLocation) => ReactNode;

export type FieldIssue = Omit<SchemaIssue, "pointer"> & { pointer?: string };

export type FieldProps<Node extends SchemaNode = SchemaNode> = FieldLocation & {
  node: Node;
  readOnly: boolean;
  issues: readonly FieldIssue[];
  change: (value: unknown) => void;
  render: RenderField;
  issuesFor: (pointer: string) => readonly FieldIssue[];
  hasIssues: (pointer: string) => boolean;
};

export interface ControlProps {
  id: string;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
  "aria-required"?: true;
}

export function FieldFrame({
  field, children, group = false, hints = [],
}: {
  field: FieldProps;
  children: (control: ControlProps) => ReactNode;
  group?: boolean;
  hints?: readonly string[];
}) {
  const id = useId();
  const { node, pointer, value, required, issues } = field;
  const description = node.description;
  const messages = [...new Set([...advisoryHints(node, value, required === true), ...hints])];
  const control: ControlProps = {
    id,
    ...(issues.length ? { "aria-invalid": true } : {}),
    ...(description || messages.length || issues.length ? { "aria-describedby": `${id}-details` } : {}),
  };
  const title = escapeText(node.title || field.label);
  const destination = helpDestination(node.ui.helpUrl);
  const details = description || messages.length > 0 || issues.length > 0 ? (
    <div id={`${id}-details`}>
      {description && <p>{escapeText(description)}</p>}
      {messages.map((message) => <p key={message}>{escapeText(message)}</p>)}
      <FieldIssues issues={issues} />
    </div>
  ) : null;
  const help = destination?.origin && <a href={destination.href} rel="noopener noreferrer">Справка ({destination.origin})</a>;
  const location = { "data-pointer": escapeText(pointer), "data-widget": node.widget };
  if (group) {
    return (
      <fieldset {...location} {...control}>
        <legend>{title}{required && " (обязательное поле)"}</legend>
        {children(control)}
        {details}
        {help}
      </fieldset>
    );
  }
  return (
    <div {...location}>
      <label htmlFor={id}>{title}{required && <span aria-hidden="true"> *</span>}</label>
      {children({ ...control, ...(required ? { "aria-required": true } : {}) })}
      {details}
      {help}
    </div>
  );
}

function helpDestination(url: string | undefined) {
  if (!url || !/^https?:\/\//iu.test(url) || escapeText(url) !== url) return null;
  try {
    const decoded = decodeURIComponent(url);
    return escapeText(decoded) === decoded ? sanitizeLink(url) : null;
  } catch {
    return null;
  }
}

export function FieldIssues({ issues }: { issues: readonly FieldIssue[] }) {
  return issues.length > 0 && (
    <ul role="alert">
      {issues.map(({ code, message, pointer }, index) => (
        <li key={index} data-code={escapeText(code)} data-issue-pointer={pointer === undefined ? undefined : escapeText(pointer)}>
          {escapeText(message)}
        </li>
      ))}
    </ul>
  );
}
