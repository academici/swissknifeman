import { Link } from "react-router";
import type { ViewLink } from "../contracts";
import { linkPath, useCatalog } from "../app/catalog";

export type Scalar = string | number | boolean | null;

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status status-${status.replace(/[^a-z_-]/g, "")}`}>{status}</span>;
}

export function formatScalar(value: Scalar | undefined): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

export function ViewLinkTo({ link, projectId, children }: { link?: ViewLink; projectId?: string; children: React.ReactNode }) {
  const catalog = useCatalog();
  const path = link ? linkPath(catalog.data, link, projectId) : null;
  return path ? <Link to={path}>{children}</Link> : <>{children}</>;
}
