import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import type { WhoAmIView } from "../api/generated/access";

export interface RouteEntry {
  readonly path: string;
  readonly page: LazyExoticComponent<ComponentType>;
  readonly public?: boolean;
  readonly nav?: {
    readonly group: "work" | "instance" | "knowledge";
    readonly label: string;
    readonly module?: "knowledge" | "learning";
  };
}

const planPage = lazy(() => import("../features/plans/PlanPage"));
export const NotFoundPage = lazy(() => import("./NotFoundPage"));

export const ROUTES: readonly RouteEntry[] = [
  { path: "/login", page: lazy(() => import("../features/auth/LoginPage")), public: true },
  { path: "/", page: lazy(() => import("../features/home/HomePage")), nav: { group: "work", label: "Главная" } },
  { path: "/w/:workspaceSlug", page: lazy(() => import("../features/workspaces/WorkspacePage")) },
  { path: "/p/:projectId", page: lazy(() => import("../features/projects/ProjectPage")) },
  {
    path: "/p/:projectId/plans", page: lazy(() => import("../features/plans/PlansPage")),
    nav: { group: "work", label: "Планы" },
  },
  { path: "/plans/:planId", page: planPage },
  { path: "/plans/:planId/drafts/:draftId", page: lazy(() => import("../features/plans/DraftEditorPage")) },
  { path: "/plans/:planId/revisions/:revisionId", page: planPage },
  { path: "/plans/:planId/revisions/:revisionId/diff/:againstId", page: lazy(() => import("../features/plans/RevisionDiffPage")) },
  {
    path: "/p/:projectId/runs", page: lazy(() => import("../features/runs/RunsPage")),
    nav: { group: "work", label: "Запуски" },
  },
  {
    path: "/p/:projectId/analytics", page: lazy(() => import("../features/analytics/AnalyticsPage")),
    nav: { group: "work", label: "Аналитика" },
  },
  {
    path: "/p/:projectId/autopilot", page: lazy(() => import("../features/autopilot/AutopilotTab")),
    nav: { group: "work", label: "Автопилот" },
  },
  { path: "/runs/:runId", page: lazy(() => import("../features/runs/RunPage")) },
  { path: "/tasks/:taskId", page: lazy(() => import("../features/runs/TaskPage")) },
  { path: "/attempts/:attemptId", page: lazy(() => import("../features/runs/AttemptPage")) },
  { path: "/steps/:stepId/context", page: lazy(() => import("../features/runs/ContextExplainPanel")) },
  { path: "/inbox", page: lazy(() => import("../features/inbox/InboxPage")), nav: { group: "work", label: "Входящие" } },
  {
    path: "/settings", page: lazy(() => import("../features/settings/SettingsPage")),
    nav: { group: "instance", label: "Настройки" },
  },
  {
    path: "/p/:projectId/files", page: lazy(() => import("../features/files/FilesPage")),
    nav: { group: "work", label: "Файлы" },
  },
  { path: "/files/:fileId", page: lazy(() => import("../features/files/FilePage")) },
  {
    path: "/extensions", page: lazy(() => import("../features/extensions/ExtensionsPage")),
    nav: { group: "instance", label: "Расширения" },
  },
  { path: "/extensions/packs/:packId", page: lazy(() => import("../features/extensions/PackPage")) },
  { path: "/extensions/resources/:resourceVersionId", page: lazy(() => import("../features/extensions/ResourcePage")) },
  {
    path: "/admin/principals", page: lazy(() => import("../features/access/PrincipalsPage")),
    nav: { group: "instance", label: "Принципалы" },
  },
  {
    path: "/admin/tokens", page: lazy(() => import("../features/access/TokensPage")),
    nav: { group: "instance", label: "Токены" },
  },
  { path: "/workers", page: lazy(() => import("../features/workers/WorkersPage")), nav: { group: "instance", label: "Воркеры" } },
  { path: "/runtimes", page: lazy(() => import("../features/workers/RuntimesPage")), nav: { group: "instance", label: "Среды выполнения" } },
  { path: "/health", page: lazy(() => import("../features/workers/HealthPage")), nav: { group: "instance", label: "Состояние системы" } },
  {
    path: "/memory", page: lazy(() => import("../features/knowledge/MemoryPage")),
    nav: { group: "knowledge", label: "Память", module: "knowledge" },
  },
  {
    path: "/lessons", page: lazy(() => import("../features/knowledge/LessonsPage")),
    nav: { group: "knowledge", label: "Уроки", module: "knowledge" },
  },
  {
    path: "/learning", page: lazy(() => import("../features/knowledge/CandidatesPage")),
    nav: { group: "knowledge", label: "Обучение", module: "learning" },
  },
  { path: "*", page: NotFoundPage },
];

export function isRouteEnabled(route: RouteEntry, modules: WhoAmIView["modules"]): boolean {
  const module = route.nav?.module;
  return module === undefined || modules[module] === true;
}
