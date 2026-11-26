import { useQuery } from "@tanstack/react-query";
import type { Catalog, ContributionRoute, ContributionWidget, ViewLink } from "../contracts";
import { useTransport } from "../transport/context";

export interface OwnedRoute extends ContributionRoute {
  owner: string;
}

export interface OwnedWidget extends ContributionWidget {
  owner: string;
}

/** Query key of the catalog; the plugin events invalidate it so the navigation follows Enable and Disable. */
export const CATALOG_KEY = ["catalog"] as const;

export function useCatalog() {
  const transport = useTransport();
  return useQuery({
    queryKey: CATALOG_KEY,
    queryFn: () => transport.request<Catalog>("GET", "/v1/ui/contributions"),
    staleTime: 60_000,
  });
}

export function routesOf(catalog: Catalog | undefined): OwnedRoute[] {
  return (catalog?.contributions ?? []).flatMap((entry) =>
    (entry.document.routes ?? []).map((route) => ({ ...route, owner: entry.owner })),
  );
}

export function widgetsOf(catalog: Catalog | undefined, scope: "fleet" | "project"): OwnedWidget[] {
  return (catalog?.contributions ?? []).flatMap((entry) =>
    (entry.document.widgets ?? []).filter((widget) => widget.scope === scope).map((widget) => ({ ...widget, owner: entry.owner })),
  );
}

/** Routes of a nav section without path parameters, in nav order. */
export function navRoutes(catalog: Catalog | undefined, section: string): OwnedRoute[] {
  return routesOf(catalog)
    .filter((route) => route.nav?.section === section && !route.path.includes(":"))
    .sort((a, b) => (a.nav?.order ?? 500) - (b.nav?.order ?? 500) || a.id.localeCompare(b.id));
}

/** The app path of a contribution route: `/x/<owner>/<path>` with `:params` filled in; `null` when one is missing. */
export function routePath(route: OwnedRoute, params: Record<string, string | undefined> = {}, projectId?: string): string | null {
  const parts: string[] = [];
  for (const part of route.path.split("/")) {
    if (part.startsWith(":")) {
      const value = params[part.slice(1)];
      if (value === undefined) return null;
      parts.push(encodeURIComponent(value));
    } else {
      parts.push(part);
    }
  }
  const query = route.scope !== "fleet" && projectId ? `?project=${encodeURIComponent(projectId)}` : "";
  return `/x/${route.owner}/${parts.join("/")}${query}`;
}

export function linkPath(catalog: Catalog | undefined, link: ViewLink, projectId?: string): string | null {
  const route = routesOf(catalog).find((candidate) => candidate.id === link.route);
  return route ? routePath(route, link.params ?? {}, projectId) : null;
}

/** The route of an owner whose path matches `rest`, with the values of its `:params`. */
export function matchRoute(
  catalog: Catalog | undefined,
  owner: string,
  rest: string,
): { route: OwnedRoute; params: Record<string, string> } | null {
  const given = rest.split("/").filter(Boolean);
  for (const route of routesOf(catalog).filter((candidate) => candidate.owner === owner)) {
    const parts = route.path.split("/");
    if (parts.length !== given.length) continue;
    const params: Record<string, string> = {};
    let ok = true;
    parts.forEach((part, index) => {
      const value = given[index] ?? "";
      if (part.startsWith(":")) params[part.slice(1)] = decodeURIComponent(value);
      else if (part !== value) ok = false;
    });
    if (ok) return { route, params };
  }
  return null;
}
