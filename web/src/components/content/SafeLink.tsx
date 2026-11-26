import { Children, cloneElement, isValidElement, type ReactNode } from "react";
import { sanitizeLink } from "../../lib/safeLink";
import { escapeText } from "../../lib/safeText";

function escapeLabel(label: ReactNode): ReactNode {
  if (typeof label === "string") return escapeText(label);
  if (isValidElement<{ children?: ReactNode }>(label) && label.props.children !== undefined) {
    return cloneElement(label, undefined, escapeLabel(label.props.children));
  }
  if (label !== null && typeof label === "object" && Symbol.iterator in label) {
    return Children.map(label, escapeLabel);
  }
  return label;
}

export function SafeLink({ href, title, children }: {
  href: string | undefined;
  title?: string | undefined;
  children: ReactNode;
}) {
  const destination = href === undefined ? null : sanitizeLink(href);
  const label = escapeLabel(children);
  if (!destination) return <span>{label}</span>;

  return (
    <a
      href={destination.href}
      title={title === undefined ? undefined : escapeText(title)}
      target={destination.origin === null ? undefined : "_blank"}
      rel={destination.origin === null ? undefined : "noopener noreferrer"}
    >
      {label}
      {destination.origin !== null && <> <bdi className="link-origin">({destination.origin})</bdi></>}
    </a>
  );
}
