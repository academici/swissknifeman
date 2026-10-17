import { NavLink, Route, Routes } from "react-router";
import type { Bootstrap } from "../contracts";
import { ConfigEditor } from "../pages/ConfigEditor";
import { ConfigModules } from "../pages/ConfigModules";
import { CatalogPage } from "../pages/CatalogPage";
import { ContributionRoute } from "../pages/ContributionRoute";
import { Dashboard } from "../pages/Dashboard";
import { PluginPage } from "../pages/PluginPage";
import { Plugins } from "../pages/Plugins";
import { ProjectPage, Projects } from "../pages/Projects";
import { RunPage, Runs } from "../pages/Runs";
import { useGuiPluginEvents } from "../plugins/useGuiPluginEvents";
import { BootstrapGate } from "./BootstrapGate";
import { navRoutes, routePath, useCatalog } from "./catalog";
import { ErrorBoundary } from "./ErrorView";

function Navigation() {
  const catalog = useCatalog();
  const sections = ["fleet", "plan", "settings", "plugins"] as const;
  return (
    <nav className="sidebar">
      <NavLink to="/" end>
        Dashboard
      </NavLink>
      <NavLink to="/projects">Projects</NavLink>
      <NavLink to="/runs">Runs</NavLink>
      <NavLink to="/catalog">Catalog</NavLink>
      <NavLink to="/plugins">Plugins</NavLink>
      {sections.map((section) => {
        const routes = navRoutes(catalog.data, section);
        if (routes.length === 0 && section !== "settings") return null;
        return (
          <div key={section} className="nav-section">
            <div className="nav-title">{section}</div>
            {section === "settings" && <NavLink to="/settings/config">Configuration</NavLink>}
            {routes.map((route) => {
              const path = routePath(route);
              return path ? (
                <NavLink key={route.id} to={path}>
                  {route.title}
                </NavLink>
              ) : null;
            })}
          </div>
        );
      })}
    </nav>
  );
}

function Shell({ bootstrap }: { bootstrap: Bootstrap }) {
  useGuiPluginEvents(); // a plugin that is enabled or disabled changes the catalog and so the navigation
  return (
    <div className="shell">
      <header>
        <span className="brand">SKM GUI</span>
        <span className="muted">
          backend {bootstrap.backend.version} · {bootstrap.platform.os}/{bootstrap.platform.arch}
        </span>
      </header>
      <Navigation />
      <main>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/:projectId" element={<ProjectPage />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/runs/:runId" element={<RunPage />} />
            <Route path="/catalog" element={<CatalogPage />} />
            <Route path="/plugins" element={<Plugins />} />
            <Route path="/plugins/:pluginId" element={<PluginPage />} />
            <Route path="/settings/config" element={<ConfigModules />} />
            <Route path="/settings/config/:module" element={<ConfigEditor />} />
            <Route path="/x/:owner/*" element={<ContributionRoute />} />
            <Route path="*" element={<div className="muted">Nothing here.</div>} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}

export function App() {
  return (
    <ErrorBoundary>
      <BootstrapGate>{(bootstrap) => <Shell bootstrap={bootstrap} />}</BootstrapGate>
    </ErrorBoundary>
  );
}
