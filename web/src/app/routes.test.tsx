// @vitest-environment jsdom
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../tests/fakeTransport";
import type { Uuid } from "../api/generated/kernel";
import { tokenStore } from "../features/auth/tokenStore";
import { App } from "./App";
import { ROUTES } from "./routes";
import "../../tests/setup";

const specification = [
  ["/login", "/login", "Вход в SKM"],
  ["/", "/", "Главная"],
  ["/w/:workspaceSlug", "/w/example", "Рабочее пространство"],
  ["/p/:projectId", "/p/project-a", "Проект"],
  ["/p/:projectId/plans", "/p/project-a/plans", "Планы"],
  ["/plans/:planId", "/plans/plan", "План"],
  ["/plans/:planId/drafts/:draftId", "/plans/plan/drafts/draft", "Редактор черновика"],
  ["/plans/:planId/revisions/:revisionId", "/plans/plan/revisions/revision", "План"],
  ["/plans/:planId/revisions/:revisionId/diff/:againstId", "/plans/plan/revisions/revision/diff/base", "Сравнение ревизий"],
  ["/p/:projectId/runs", "/p/project-a/runs", "Запуски"],
  ["/p/:projectId/analytics", "/p/project-a/analytics", "Аналитика ревью"],
  ["/p/:projectId/autopilot", "/p/project-a/autopilot", "Автопилот"],
  ["/runs/:runId", "/runs/run", "Запуск"],
  ["/tasks/:taskId", "/tasks/task", "Задача"],
  ["/attempts/:attemptId", "/attempts/attempt", "Попытка"],
  ["/steps/:stepId/context", "/steps/step/context", "Контекст шага"],
  ["/inbox", "/inbox", "Входящие"],
  ["/settings", "/settings", "Настройки"],
  ["/p/:projectId/files", "/p/project-a/files", "Файлы"],
  ["/files/:fileId", "/files/file", "Файл"],
  ["/extensions", "/extensions", "Расширения"],
  ["/extensions/packs/:packId", "/extensions/packs/pack", "Пакет расширений"],
  ["/extensions/resources/:resourceVersionId", "/extensions/resources/resource", "Ресурс расширения"],
  ["/admin/principals", "/admin/principals", "Принципалы"],
  ["/admin/tokens", "/admin/tokens", "Токены доступа"],
  ["/workers", "/workers", "Воркеры"],
  ["/runtimes", "/runtimes", "Среды выполнения"],
  ["/health", "/health", "Состояние системы"],
  ["/memory", "/memory", "Память"],
  ["/lessons", "/lessons", "Уроки"],
  ["/learning", "/learning", "Обучение"],
  ["*", "/unknown/route", "Страница не найдена"],
] as const;

function open(path: string, token: string | null = "valid-token") {
  history.replaceState(null, "", path);
  if (token !== null) tokenStore.set(token);
  render(<App initialToken={token} />);
}

const workspace = { workspace_id: "ws-a", title: "Пример пространства", slug: "example", state: "active" };
const project = { project_id: "project-a", workspace_id: workspace.workspace_id, title: "Пример проекта", state: "active" };
const file = { file_id: "file", workspace_id: workspace.workspace_id, project_id: project.project_id,
  title: "Заметки", state: "active", origin: "upload", classification: "internal", current_version: { version_no: 1 } };

async function workspaceFetch(input: RequestInfo | URL) {
  const { pathname } = new URL(String(input), window.location.origin);
  switch (pathname) {
    case "/api/v1/me": return Response.json(testIdentity);
    case "/api/v1/workspaces": return Response.json({ items: [workspace], next: null });
    case "/api/v1/workspaces/ws-a": return Response.json(workspace);
    case "/api/v1/workspaces/ws-a/projects": return Response.json({ items: [project], next: null });
    case "/api/v1/projects/project-a": return Response.json(project);
    case "/api/v1/files": return Response.json({ items: [file], next: null });
    case "/api/v1/files/file": return Response.json(file);
    case "/api/v1/files/file/versions": return Response.json({ items: [], next: null });
    default: throw new Error(`Unexpected request ${pathname}`);
  }
}

const workspaceRoutes = ["/w/:workspaceSlug", "/p/:projectId", "/p/:projectId/files", "/files/:fileId"];
const executionRoutes = ["/p/:projectId/runs", "/p/:projectId/analytics", "/p/:projectId/autopilot", "/runs/:runId", "/tasks/:taskId", "/attempts/:attemptId", "/steps/:stepId/context"];

const routeRun = {
  run_id: "run", plan_id: "plan", plan_alias: "PLAN1", revision_no: 2, status: "running", kind: "plan",
  counts_by_status: {}, row_version: 1,
};

async function executionFetch(input: RequestInfo | URL) {
  const { pathname } = new URL(String(input), window.location.origin);
  switch (pathname) {
    case "/api/v1/projects/project-a/autopilot": return Response.json({
      effective_state: "disabled", state: "idle", emergency: false, current_run_id: null,
      queue: [], counters: {}, stop_code: null, stop_detail: null, session_started_at: null,
    });
    case "/api/v1/projects/project-a/autopilot/explain": return Response.json({ status: {}, keys: [], stop_conditions: [] });
    case "/api/v1/projects/project-a/runs": return Response.json({ items: [routeRun], next_after: null });
    case "/api/v1/runs/run": return Response.json(routeRun);
    case "/api/v1/execution/detail": return Response.json({
      run_id: "run", workspace_id: workspace.workspace_id, project_id: project.project_id, plan_id: "plan",
      revision_id: "revision", row_version: 1,
    });
    case "/api/v1/runs/run/tasks": return Response.json({ tasks: [], edges: [] });
    case "/api/v1/tasks/task": return Response.json({ task_id: "task", display_key: "P1.2", status: "executing", attempts: [] });
    case "/api/v1/tasks/task/attempts": return Response.json({ attempts: [] });
    case "/api/v1/attempts/attempt": return Response.json({
      attempt_id: "attempt", attempt_no: 2, state: "completed", stages: [], steps: [],
      outputs: [], checks: [], reviews: [], findings: [], effects: [], recoveries: [],
    });
    case "/api/v1/steps/step": return Response.json({});
    default: return workspaceFetch(input);
  }
}

describe("Routes", () => {
  it("declares exactly the paths in web §3", () => {
    expect(ROUTES.map(({ path }) => path).sort()).toEqual(specification.map(([path]) => path).sort());
  });

  it.each(specification)("%s renders its heading", async (pattern, path, heading) => {
    const planning = pattern === "/p/:projectId/plans" || pattern.startsWith("/plans/");
    if (planning) {
      stubFetch(async (input) => {
        const { pathname } = new URL(String(input), window.location.origin);
        switch (pathname) {
          case "/api/v1/me": return Response.json(testIdentity);
          case "/api/v1/plans/plan": return Response.json({
            plan_id: "plan", alias: "PLAN1", title: "Первый план", lifecycle_state: "active",
            current_revision_id: null, current_revision_no: null, open_drafts: 0, row_version: 1,
          });
          case "/api/v1/projects/project-a/plans":
          case "/api/v1/plans/plan/revisions":
          case "/api/v1/plans/plan/entities": return Response.json({ items: [], next_cursor: null });
          case "/api/v1/plans/plan/drafts/draft": return Response.json({
            draft_id: "draft", state: "open", edit_version: 1, base_revision_id: null, base_revision_no: null,
            document: { title: "Черновик плана", phases: [], items: [] },
          });
          case "/api/v1/plans/plan/drafts/draft/validate": return Response.json({
            edit_version: 1, schema_issues: [], findings: [], rule_failures: [],
          });
          case "/api/v1/plans/plan/revisions/revision": return Response.json({ tree: { phases: [] } });
          case "/api/v1/plans/plan/revisions/revision/diff": return Response.json({
            from: {}, to: {}, from_digest: "a", to_digest: "b", summary: {}, plan_fields: [], entities: [],
          });
          case "/api/v1/projects/project-a": return Response.json({ workspace_id: null });
          default: throw new Error(`Unexpected request ${pathname}`);
        }
      });
    } else if (pattern === "/settings") {
      stubFetch(async (input) => {
        const { pathname } = new URL(String(input), window.location.origin);
        switch (pathname) {
          case "/api/v1/me": return Response.json(testIdentity);
          case "/api/v1/config/schema": return Response.json({ registry_digest: "registry", sections: [] });
          case "/api/v1/config/explain": return Response.json({
            schema: "urn:skm:config:explain:v1", scope: { level: "instance" },
            chain: [{ level: "instance" }], generation: 7, digest: "digest", keys: [],
          });
          case "/api/v1/config/entries": return Response.json({ items: [], next: null });
          case "/api/v1/config/export": return Response.json({ entries: [], digest: "digest", format: "json", document: {} });
          default: throw new Error(`Unexpected request ${pathname}`);
        }
      });
    } else if (pattern === "/health") {
      stubFetch(async input => String(input) === "/health/live" ? Response.json({ status: "live" })
        : String(input) === "/health/ready" ? Response.json({ status: "ready", checks: { database: "ok", schema: "ok", background: "ok" } })
        : workspaceFetch(input));
    } else if (workspaceRoutes.includes(pattern)) {
      stubFetch(workspaceFetch);
    } else if (executionRoutes.includes(pattern)) {
      stubFetch(executionFetch);
    } else if (pattern === "/admin/principals") {
      stubFetch(async input => new URL(String(input), location.origin).pathname === "/api/v1/principals"
        ? Response.json({ items: [], next: null }) : Response.json(testIdentity));
    } else if (pattern === "/admin/tokens") {
      stubFetch(async input => new URL(String(input), location.origin).pathname === "/api/v1/me"
        ? Response.json({ ...testIdentity, effective_permissions: ["token.own"] })
        : Response.json({ items: [], next: null }));
    } else {
      stubFetch();
    }
    open(path, pattern === "/login" ? null : "valid-token");
    await screen.findByRole("heading", { name: heading, level: 1 });
    if (pattern === "/settings") {
      expect(await screen.findByText("Область доступна для чтения.")).toBeTruthy();
      expect(screen.getByText(/Поколение 7/)).toBeTruthy();
      expect(screen.getByRole("button", { name: "Экспорт" })).toBeTruthy();
    } else if (pattern === "/w/:workspaceSlug") {
      expect(await screen.findByRole("link", { name: project.title })).toBeTruthy();
    } else if (pattern === "/p/:projectId") {
      expect(await screen.findByRole("heading", { name: project.title })).toBeTruthy();
    } else if (pattern === "/p/:projectId/files") {
      expect(await screen.findByRole("link", { name: file.title })).toBeTruthy();
    } else if (pattern === "/files/:fileId") {
      expect(await screen.findByRole("heading", { name: file.title })).toBeTruthy();
      expect(await screen.findByRole("heading", { name: "Нет версий" })).toBeTruthy();
    } else if (planning) {
      const content = pattern.includes("/diff/") ? "Изменений нет" : pattern.includes("/drafts/") ? "Черновик плана"
        : pattern === "/p/:projectId/plans" ? "Планов нет" : "PLAN1 · Первый план";
      expect(await screen.findByRole("heading", { name: content })).toBeTruthy();
    } else if (pattern === "/p/:projectId/autopilot") {
      expect(await screen.findByRole("heading", { name: "Состояние автопилота" })).toBeTruthy();
      expect(await screen.findByRole("heading", { name: "Объяснение" })).toBeTruthy();
    } else if (pattern === "/p/:projectId/runs") {
      expect((await screen.findByRole("link", { name: "PLAN1 · r2" })).getAttribute("href")).toBe("/runs/run?project_id=project-a");
    } else if (pattern === "/p/:projectId/analytics") {
      expect(await screen.findByRole("combobox", { name: "Запуск" })).toBeTruthy();
    } else if (pattern === "/runs/:runId") {
      expect(await screen.findByRole("heading", { name: /PLAN1 · r2/u })).toBeTruthy();
      expect(await screen.findByRole("heading", { name: "Нет задач" })).toBeTruthy();
    } else if (pattern === "/tasks/:taskId") {
      expect(await screen.findByRole("heading", { name: /P1.2/u })).toBeTruthy();
      expect((await screen.findByRole("link", { name: "К запуску" })).getAttribute("href")).toBe("/runs/run?project_id=project-a");
    } else if (pattern === "/attempts/:attemptId") {
      expect(await screen.findByRole("heading", { name: /Попытка 2/u })).toBeTruthy();
      expect(await screen.findByRole("heading", { name: "Нет проверок" })).toBeTruthy();
    } else if (pattern === "/steps/:stepId/context") {
      expect(await screen.findByText("Манифест контекста недоступен.")).toBeTruthy();
    } else if (pattern === "/admin/principals") {
      expect(await screen.findByRole("heading", { name: "Нет принципалов" })).toBeTruthy();
    } else if (pattern === "/admin/tokens") {
      expect(await screen.findByRole("heading", { name: "Нет активных токенов" })).toBeTruthy();
    } else if (pattern.startsWith("/extensions") || pattern === "/workers" || pattern === "/runtimes") {
      expect(screen.getByRole("alert").textContent).toContain("Нет доступа");
    } else if (pattern === "/health") {
      expect(screen.getByRole("heading", { name: "Готовность" })).toBeTruthy();
    } else if (pattern === "/inbox") {
      expect(screen.getByRole("combobox", { name: "Тип" })).toBeTruthy();
      expect(screen.getByRole("textbox", { name: "Область" })).toBeTruthy();
    } else if (pattern === "/memory" || pattern === "/lessons" || pattern === "/learning") {
      expect(screen.getByText(pattern === "/memory" ? "Выберите проект." : "Выберите рабочее пространство.")).toBeTruthy();
    } else if (pattern !== "*" && pattern !== "/login") {
      expect(screen.getByText("Раздел ещё не реализован.")).toBeTruthy();
    }
  });

  it("starts a run directly from the displayed plan and selected revision", async () => {
    const requests: { path: string; body: unknown }[] = [];
    stubFetch(async (input, init) => {
      const { pathname } = new URL(String(input), window.location.origin);
      if (init?.method === "POST") requests.push({ path: pathname, body: JSON.parse(String(init.body)) });
      switch (pathname) {
        case "/api/v1/me": return Response.json({ ...testIdentity, permissions_by_scope: { plan: ["run.start"] } });
        case "/api/v1/plans/plan": return Response.json({
          plan_id: "plan", alias: "PLAN1", title: "Первый план", lifecycle_state: "active",
          current_revision_id: "current", current_revision_no: 3, open_drafts: 0, project_id: project.project_id,
        });
        case "/api/v1/plans/plan/revisions": return Response.json({
          items: [{ revision_id: "current", revision_no: 3 }, { revision_id: "revision", revision_no: 2 }],
        });
        case "/api/v1/plans/plan/revisions/revision": return Response.json({ tree: { phases: [] } });
        case "/api/v1/plans/plan/revisions/revision/readiness": return Response.json({
          report_id: "report-selected", status: "ready", findings: [], estimate: {}, work_policies: {},
        });
        case "/api/v1/plans/plan/runs": return Response.json({ run_id: "run" }, { status: 201 });
        default: return executionFetch(input);
      }
    });
    open("/plans/plan/revisions/revision");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Запустить" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Новый запуск" }));
    expect(dialog.getByText("revision")).toBeTruthy();
    await user.click(dialog.getByRole("button", { name: "Проверить готовность" }));
    await user.type(dialog.getByRole("textbox", { name: "Причина" }), "Запуск r2");
    const start = dialog.getByRole<HTMLButtonElement>("button", { name: "Запустить" });
    await waitFor(() => expect(start.disabled).toBe(false));
    await user.click(start);
    await waitFor(() => expect(location.pathname).toBe("/runs/run"));
    expect(requests).toEqual([
      { path: "/api/v1/plans/plan/revisions/revision/readiness", body: { overrides: {} } },
      { path: "/api/v1/plans/plan/runs", body: {
        overrides: {}, revision_id: "revision", readiness_report_id: "report-selected", reason: "Запуск r2",
      } },
    ]);
  });

  it("renders the workspace directory from the workspace route", async () => {
    stubFetch(workspaceFetch);
    open("/w/example?view=workspaces");
    await screen.findByRole("heading", { name: "Рабочие пространства", level: 1 });
    expect(await screen.findByRole("link", { name: workspace.title })).toBeTruthy();
  });

  it("updates the top bar's scoped open inbox count on an SSE decision event", async () => {
    const inboxReads: URL[] = [];
    let items = [{ request_id: "decision-a" }];
    let feed: ReadableStreamDefaultController<Uint8Array> | undefined;
    let cursor = 7;
    stubFetch(async input => {
      const url = new URL(String(input), location.origin);
      if (url.pathname === "/api/v1/me") {
        return Response.json({ ...testIdentity, permissions_by_scope: { [project.project_id]: ["inbox.read"] } });
      }
      if (url.pathname === "/api/v1/inbox") {
        inboxReads.push(url);
        return Response.json({ items, next_after: null }, { headers: { "SKM-Events-Cursor": String(cursor) } });
      }
      if (url.pathname === "/api/v1/events") {
        return new Response(new ReadableStream({ start(controller) { feed = controller; } }), {
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      return workspaceFetch(input);
    });
    open(`/p/${project.project_id}?workspace_id=${workspace.workspace_id}`);
    const topBar = within(await screen.findByRole("banner"));
    await topBar.findByRole("link", { name: "Входящие (1)" });
    await waitFor(() => expect(feed).toBeDefined());
    items = [];
    cursor += 1;
    const event = {
      type: "urn:skm:execution:event:decision-answered:v1", workspace_id: workspace.workspace_id,
      stream_kind: "run", stream_id: "run", payload: { request_id: "decision-a" },
    };
    await act(async () => feed?.enqueue(new TextEncoder().encode(`id: ${cursor}\nevent: message\ndata: ${JSON.stringify(event)}\n\n`)));
    await topBar.findByRole("link", { name: "Входящие (0)" });
    expect(inboxReads.map(url => [url.searchParams.get("scope"), url.searchParams.get("states")])).toEqual([
      [`project:${project.project_id}`, "open"], [`project:${project.project_id}`, "open"],
    ]);
  });

  it.each([
    [{ knowledge: false, learning: false }, []],
    [{ knowledge: true, learning: false }, ["Память", "Уроки"]],
    [{ knowledge: false, learning: true }, ["Обучение"]],
    [{}, []],
  ] as const)("shows only optional nav reported enabled by /me (%j)", async (modules, visible) => {
    stubFetch(async () => Response.json({ ...testIdentity, modules }));
    open("/");
    const nav = within(await screen.findByRole("navigation", { name: "Основная навигация" }));
    for (const label of ["Память", "Уроки", "Обучение"] as const) {
      expect(nav.queryByRole("link", { name: label }) !== null).toBe((visible as readonly string[]).includes(label));
    }
    expect(nav.getByRole("link", { name: "Настройки" })).toBeTruthy();
  });

  it.each(["/memory", "/lessons", "/learning"])("blocks direct navigation to disabled %s", async (path) => {
    stubFetch(async () => Response.json({ ...testIdentity, modules: {} }));
    open(path);
    await screen.findByRole("heading", { name: "Страница не найдена" });
  });

  it("prefers the project in the URL to stored scope and builds project nav from it", async () => {
    stubFetch(async (input) => String(input).startsWith("/api/v1/projects/project-a/plans")
      ? Response.json({ items: [], next_cursor: null }) : Response.json(testIdentity));
    sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws-a", projectId: "project-old" }));
    open("/p/project-a/plans");
    const nav = within(await screen.findByRole("navigation", { name: "Основная навигация" }));
    expect(nav.getByRole("link", { name: "Запуски" }).getAttribute("href")).toBe("/p/project-a/runs");
    expect(nav.getByRole("link", { name: "Планы" }).getAttribute("aria-current")).toBe("page");
    await waitFor(() => expect(JSON.parse(sessionStorage.getItem("skm.scope") ?? "null")).toMatchObject({
      workspaceId: null, projectId: "project-a",
    }));
  });

  it("uses an explicit workspace from the URL and isolates workspace slug navigation", async () => {
    stubFetch(workspaceFetch);
    sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws-old", projectId: "project-old" }));
    open("/w/example?workspace_id=ws-a");
    await screen.findByRole("heading", { name: "Рабочее пространство", level: 1 });
    expect(JSON.parse(sessionStorage.getItem("skm.scope") ?? "null")).toEqual({
      workspaceId: "ws-a", projectId: null, workspaceSlug: "example",
    });
  });

  it("restores saved scope and switches to a project granted by /me", async () => {
    stubFetch(async input => {
      const { pathname } = new URL(String(input), window.location.origin);
      if (pathname === "/api/v1/me") return Response.json({
        ...testIdentity,
        memberships: [{ scope_kind: "project", scope_id: "project-next" as Uuid }],
      });
      if (pathname === "/api/v1/projects/project-next") return Response.json({ ...project, project_id: "project-next" });
      return workspaceFetch(input);
    });
    sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws-a", projectId: "project-a" }));
    open("/");
    const project = await screen.findByRole<HTMLSelectElement>("combobox", { name: "Проект" });
    expect(project.value).toBe("project-a");
    await userEvent.selectOptions(project, "project-next");
    await screen.findByRole("heading", { name: "Проект", level: 1 });
    expect(location.pathname).toBe("/p/project-next");
    expect(sessionStorage.getItem("skm.scope")).toContain('"projectId":"project-next"');
  });
});
