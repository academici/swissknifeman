import { CSPProvider } from "@base-ui/react/csp-provider";
import { skipToken, useQuery } from "@tanstack/react-query";
import { Suspense } from "react";
import { BrowserRouter, matchPath, Navigate, Outlet, Route, Routes, useLocation } from "react-router";
import { ApiError } from "../api/errors";
import type { ExplainReport } from "../api/generated/settings";
import type { WorkspaceView } from "../api/generated/workspace";
import { keys } from "../api/keys";
import { ErrorPanel } from "../components/feedback/ErrorPanel";
import { Spinner } from "../components/primitives/Spinner";
import { ErrorBoundary } from "./ErrorBoundary";
import { Shell } from "./layout/Shell";
import { AuthProvider, useAuth } from "./providers/AuthProvider";
import { QueryProvider } from "./providers/QueryProvider";
import { ScopeProvider, useScope } from "./providers/ScopeProvider";
import { StreamProvider, useStream } from "./providers/StreamProvider";
import { ToastProvider } from "./providers/ToastProvider";
import { isRouteEnabled, NotFoundPage, ROUTES, type RouteEntry } from "./routes";

function RequireIdentity() {
  const { status, me, identityError, refreshIdentity, signOut, logoutError, sessionActionPending } = useAuth();
  const { pathname } = useLocation();
  if (status === "probing") return <main className="login"><Spinner label="Проверка сеанса…" /></main>;
  if (status !== "authenticated") return <Navigate to="/login" replace />;
  if (me) return <Outlet />;
  if (identityError instanceof ApiError && identityError.status === 409 &&
      identityError.code === "SCHEMA_NOT_MIGRATED" && matchPath("/health", pathname)) return <Outlet />;
  if (identityError) {
    return (
      <main className="login">
        <ErrorPanel error={identityError} onRetry={refreshIdentity} />
        <button type="button" disabled={sessionActionPending} onClick={() => { void signOut(); }}>Использовать другой токен</button>
        {logoutError && <p role="alert">{logoutError}</p>}
      </main>
    );
  }
  return <main className="login"><Spinner label="Проверка сеанса…" /></main>;
}

function routeElement(route: RouteEntry, enabled = true) {
  const Page = enabled ? route.page : NotFoundPage;
  return <Route key={route.path} path={route.path} element={<Page />} />;
}

function WorkspaceShell() {
  const { transport } = useAuth();
  const { scope } = useScope();
  const { readWithEvents } = useStream();
  const { workspaceId } = scope;
  useQuery({
    queryKey: [...keys.scope(scope), "workspace-detail"],
    queryFn: workspaceId === null ? skipToken : async ({ signal }) => {
      const path = `/api/v1/workspaces/${encodeURIComponent(workspaceId)}`;
      const response = await readWithEvents(() => transport.request<WorkspaceView>("GET", path, { signal }), signal);
      return response.data;
    },
  });
  return <Shell />;
}

const staleAfterKey = "ui.stale_after_seconds";

function AuthenticatedShell() {
  const { me, transport } = useAuth();
  const { data: staleAfterSeconds } = useQuery({
    queryKey: ["config", "instance", staleAfterKey],
    enabled: me?.effective_permissions.includes("config.read") === true,
    queryFn: async ({ signal }) => {
      const { data } = await transport.request<ExplainReport>(
        "GET", `/api/v1/config/effective?scope=instance&keys=${staleAfterKey}`, { signal },
      );
      const value = data.keys.find(({ key }) => key === staleAfterKey)?.value;
      return typeof value === "number" && Number.isInteger(value) && value >= 1 && value <= 3_600 ? value : null;
    },
  });

  if (!me) return <main id="main"><Outlet /></main>;

  return (
    <ScopeProvider transport={transport}>
      <ToastProvider>
        <StreamProvider staleAfterSeconds={staleAfterSeconds ?? 30}>
          <WorkspaceShell />
        </StreamProvider>
      </ToastProvider>
    </ScopeProvider>
  );
}

export function AppRoutes() {
  const { me } = useAuth();
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        {ROUTES.filter((route) => route.public).map((route) => routeElement(route))}
        <Route element={<RequireIdentity />}>
          <Route element={<AuthenticatedShell />}>
            {ROUTES.filter((route) => !route.public).map((route) => routeElement(route, isRouteEnabled(route, me?.modules ?? {})))}
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}

export function App({ initialToken }: { initialToken: string | null }) {
  return (
    <ErrorBoundary>
      <CSPProvider disableStyleElements>
        <BrowserRouter>
          <QueryProvider>
            <AuthProvider initialToken={initialToken}>
              <AppRoutes />
            </AuthProvider>
          </QueryProvider>
        </BrowserRouter>
      </CSPProvider>
    </ErrorBoundary>
  );
}
