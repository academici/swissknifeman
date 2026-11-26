import { Suspense } from "react";
import { Outlet, useLocation } from "react-router";
import { Spinner } from "../../components/primitives/Spinner";
import { ErrorBoundary } from "../ErrorBoundary";
import { Nav } from "./Nav";
import { TopBar } from "./TopBar";

export function Shell() {
  const { pathname } = useLocation();
  return (
    <div className="shell">
      <a className="skip-link" href="#main">К содержимому</a>
      <TopBar />
      <div className="shell-body">
        <Nav />
        <main id="main" tabIndex={-1}>
          <ErrorBoundary key={pathname}>
            <Suspense fallback={<Spinner />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
