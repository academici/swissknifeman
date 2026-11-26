import { generatePath, NavLink } from "react-router";
import { useAuth } from "../providers/AuthProvider";
import { useScope } from "../providers/ScopeProvider";
import { isRouteEnabled, ROUTES } from "../routes";

const groupLabels = {
  work: "Работа",
  instance: "Администрирование",
  knowledge: "Знания",
};

export function Nav() {
  const { me } = useAuth();
  const { scope } = useScope();
  const links = ROUTES.flatMap((route) => {
    if (!route.nav || !isRouteEnabled(route, me?.modules ?? {})) return [];
    if (route.path.includes(":projectId") && !scope.projectId) return [];
    return [{
      ...route.nav,
      to: generatePath(route.path, { projectId: scope.projectId }),
    }];
  });

  return (
    <nav aria-label="Основная навигация" className="nav">
      {Object.entries(groupLabels).map(([group, title]) => {
        const entries = links.filter((link) => link.group === group);
        if (entries.length === 0) return null;
        return (
          <section key={group}>
            <h2>{title}</h2>
            <ul>
              {entries.map(({ label, to }) => (
                <li key={to}><NavLink to={to} end={to === "/"}>{label}</NavLink></li>
              ))}
            </ul>
          </section>
        );
      })}
    </nav>
  );
}
