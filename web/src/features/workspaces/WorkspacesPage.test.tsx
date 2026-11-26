// @vitest-environment jsdom
import "../../../tests/setup";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { App } from "../../app/App";
import { tokenStore } from "../auth/tokenStore";

const workspace = { workspace_id: "w1", title: "Research", slug: "research", row_version: 3, state: "active", project_count: 1 };
const project = { project_id: "p1", workspace_id: "w1", title: "Atlas", slug: "atlas", description: "Maps", state: "active", row_version: 4, mounts: [] };
const repo = { repository_id: "r1", title: "Sources", canonical_remote: null };
const workspacePath = "/w/research?workspace_id=w1";
const projectPath = "/p/p1?workspace_id=w1";
const permissions = { w1: ["workspace.read", "repo.manage", "workspace.manage", "project.create"], p1: ["project.manage", "integration.read"] };
type Handler = (url: URL, init: RequestInit) => Response | undefined;

function open(path: string, handle: Handler, writable = true) {
  const fetch = stubFetch(async (input, init = {}) => {
    const url = new URL(String(input), location.origin);
    const custom = handle(url, init);
    if (custom) return custom;
    switch (url.pathname) {
      case "/api/v1/me": return Response.json({ ...testIdentity, permissions_by_scope: writable ? permissions : { other: ["repo.manage", "project.manage"] },
        effective_permissions: writable ? ["workspace.create", "host.manage"] : [] });
      case "/api/v1/workspaces": return Response.json({ items: [workspace], next: null });
      case "/api/v1/workspaces/w1": return Response.json(workspace);
      case "/api/v1/workspaces/w1/projects": return Response.json({ items: [project], next: null });
      case "/api/v1/projects/p1": return Response.json(project);
      case "/api/v1/workspaces/w1/repositories": return Response.json({ items: [repo], next: null });
      case "/api/v1/projects/p1/repositories": return Response.json({ items: [] });
      case "/api/v1/hosts": return Response.json({ items: [], next: null });
      case "/api/v1/memberships": return Response.json({ items: [{ principal_id: "member", display_name: "Lena", role: "owner" }], next: null });
      default: throw new Error("Unexpected request " + url.pathname);
    }
  });
  tokenStore.set("workspace-token");
  history.replaceState(null, "", path);
  render(<App initialToken="workspace-token" />);
  return fetch;
}

describe("Workspace and project routes", () => {
  it("pages the workspace directory and creates a workspace", async () => {
    const user = userEvent.setup();
    let created = false;
    open(workspacePath + "&view=workspaces", (url, init) => {
      if (url.pathname !== "/api/v1/workspaces") return;
      if (init.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({ slug: "field", title: "Field" });
        expect(new Headers(init.headers).get("Idempotency-Key")).toMatch(/^web-/);
        created = true;
        return Response.json({ workspace_id: "w2" }, { status: 201 });
      }
      expect(url.searchParams.get("limit")).toBe("50");
      if (url.searchParams.get("after") === "opaque?+/") return Response.json({ items: [{ ...workspace, workspace_id: "w2", slug: "field", title: "Field" }], next: null });
      return Response.json({ items: [workspace], next: "opaque?+/" });
    });
    expect((await screen.findByRole("link", { name: "Research" }, { timeout: 5000 })).getAttribute("href")).toBe(workspacePath);
    await user.click(screen.getByRole("button", { name: "Далее" }));
    await screen.findByRole("link", { name: "Field" });
    expect(screen.queryByRole("link", { name: "Research" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Назад" }));
    await screen.findByRole("link", { name: "Research" });
    await user.click(screen.getByRole("button", { name: "Создать пространство" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByRole("textbox", { name: "Slug" }), "field");
    await user.type(dialog.getByRole("textbox", { name: "Название" }), "Field");
    await user.click(dialog.getByRole("button", { name: "Создать" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(created).toBe(true);
  });

  it("resolves a slug on a later page, creates projects and reads scoped memberships", async () => {
    const user = userEvent.setup();
    let created = false;
    open("/w/research", (url, init) => {
      if (url.pathname === "/api/v1/workspaces") {
        expect(url.searchParams.has("slug")).toBe(false);
        return Response.json(url.searchParams.has("after") ? { items: [workspace], next: null } : { items: [], next: "page2" });
      }
      if (url.pathname === "/api/v1/workspaces/w1/projects") {
        if (init.method === "POST") {
          expect(JSON.parse(String(init.body))).toEqual({ slug: "new", title: "New project", description: "Notes" });
          created = true;
          return Response.json({ project_id: "p2" }, { status: 201 });
        }
        return Response.json({ items: created ? [{ ...project, project_id: "p2", title: "New project" }] : [project], next: null });
      }
      if (url.pathname === "/api/v1/memberships") expect(url.searchParams.get("scope_id")).toBe("w1");
    });
    await screen.findByRole("heading", { name: "Research" });
    expect((await screen.findByRole("link", { name: "Atlas" })).getAttribute("href")).toBe("/p/p1");
    await user.click(screen.getByRole("button", { name: "Создать проект" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByRole("textbox", { name: "Slug" }), "new");
    await user.type(dialog.getByRole("textbox", { name: "Название" }), "New project");
    await user.type(dialog.getByRole("textbox", { name: "Описание" }), "Notes");
    await user.click(dialog.getByRole("button", { name: "Создать" }));
    await screen.findByRole("link", { name: "New project" });
    await user.click(screen.getByRole("tab", { name: "Участники" }));
    await screen.findByRole("cell", { name: "Lena" });
  });

  it("subscribes after the snapshot and refreshes the projects list on replay", async () => {
    let count = 0;
    let feed: ReadableStreamDefaultController<Uint8Array> | undefined;
    open(workspacePath, (url) => {
      if (url.pathname === "/api/v1/workspaces/w1/projects") {
        count++;
        return Response.json({ items: count === 1 ? [] : [project], next: null }, { headers: { "SKM-Events-Cursor": count === 1 ? "12" : "13" } });
      }
      if (url.pathname === "/api/v1/events") {
        expect(url.searchParams.get("workspace_id")).toBe("w1");
        if (!feed) expect(url.searchParams.get("after")).toBe("12");
        return new Response(new ReadableStream<Uint8Array>({ start(controller) { feed = controller; } }), { headers: { "Content-Type": "text/event-stream" } });
      }
    });
    await screen.findByRole("heading", { name: "Нет проектов" });
    await waitFor(() => expect(feed).toBeDefined());
    const event = { workspace_id: "w1", stream_kind: "project", stream_id: "p1", type: "ProjectCreated", payload: { project_id: "p1" } };
    act(() => feed?.enqueue(new TextEncoder().encode(`id: 13\nevent: event\ndata: ${JSON.stringify(event)}\n\n`)));
    await screen.findByRole("link", { name: "Atlas" });
  });

  it.each([false, true])("renders backend binding status with optional locator (present=%s)", async present => {
    const user = userEvent.setup();
    open(projectPath, (url) => {
      if (url.pathname.endsWith("/p1/repositories")) {
        return Response.json({ items: [{ mount_name: "main", role: "primary", repository: repo, binding: {
          state: "active", is_stale: true, ...(present && url.searchParams.has("host_id") ? { local_locator: "/local/atlas" } : {}),
        } }] });
      }
    }, false);
    await screen.findByRole("heading", { name: "Atlas" });
    for (const name of ["Overview", "Plans", "Runs", "Autopilot", "Repositories", "Files", "Integrations", "Settings"]) {
      expect(screen.getByRole("tab", { name })).toBeTruthy();
    }
    await user.click(screen.getByRole("tab", { name: "Repositories" }));
    await screen.findByRole("cell", { name: "active · Устарела" });
    await user.type(screen.getByRole("textbox", { name: "ID хоста" }), "h1");
    await user.click(screen.getByRole("button", { name: "Показать привязки" }));
    await screen.findByRole("cell", { name: present ? /\/local\/atlas/ : "active · Устарела" });
    expect(screen.queryByText("/local/atlas") !== null).toBe(present);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: "Отключить" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Зарегистрировать репозиторий" })).toBeNull();
  });

  it("registers a repository, adds a remote, attaches and detaches its mount", async () => {
    const user = userEvent.setup();
    const writes: [string, string, unknown][] = [];
    let mounted = false;
    open(projectPath, (url, init) => {
      if (init.method !== "GET") {
        writes.push([String(init.method), url.pathname, init.body ? JSON.parse(String(init.body)) : null]);
        if (url.pathname.endsWith("/p1/repositories")) mounted = true;
        if (init.method === "DELETE") mounted = false;
        return Response.json({});
      }
      if (url.pathname.endsWith("/p1/repositories")) return Response.json({ items: mounted ? [{ mount_name: "main", repository: repo, role: "primary", binding: null }] : [] });
    });
    await user.click(await screen.findByRole("tab", { name: "Repositories" }));
    await user.type(screen.getByRole("textbox", { name: "Название репозитория" }), "Sources");
    await user.click(screen.getByRole("button", { name: "Зарегистрировать репозиторий" }));
    await user.click(await screen.findByRole("button", { name: "Выбрать Sources" }));
    await user.type(screen.getByRole("textbox", { name: "Новый remote" }), "https://example.org/repo");
    await user.click(screen.getByRole("button", { name: "Добавить remote" }));
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Новый remote" })).toBeNull());
    await user.click(screen.getByRole("button", { name: "Выбрать Sources" }));
    await user.click(screen.getByRole("button", { name: "Подключить репозиторий" }));
    await user.click(await screen.findByRole("button", { name: "Отключить" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Подтвердить" }));
    await screen.findByRole("heading", { name: "Нет подключённых репозиториев" });
    expect(writes).toEqual([
      ["POST", "/api/v1/workspaces/w1/repositories", { title: "Sources", remote_url: null, external_id: null }],
      ["POST", "/api/v1/repositories/r1/remotes", { url: "https://example.org/repo", make_primary: false }],
      ["POST", "/api/v1/projects/p1/repositories", { repository_id: "r1", mount_name: "main", role: "primary" }],
      ["DELETE", "/api/v1/projects/p1/repositories/main", null],
    ]);
  });

  it("archives the workspace with its visible row version and refreshes the shell snapshot", async () => {
    const user = userEvent.setup();
    let archived = false;
    open(workspacePath, (url, init) => {
      if (url.pathname === "/api/v1/workspaces/w1/archive") {
        expect(new Headers(init.headers).get("If-Match")).toBe('W/"v3"');
        expect(JSON.parse(String(init.body))).toEqual({ reason: "Complete" });
        archived = true;
        return Response.json({ state: "archived", row_version: 4 });
      }
      if (url.pathname === "/api/v1/workspaces/w1" && archived) return Response.json({ ...workspace, state: "archived", row_version: 4 });
    });
    await user.click(await screen.findByRole("button", { name: "Архивировать" }));
    const dialog = within(await screen.findByRole("alertdialog"));
    await user.type(dialog.getByRole("textbox", { name: "Причина" }), "Complete");
    await user.click(dialog.getByRole("button", { name: "Подтвердить" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Архивировать" })).toBeNull());
    expect(await screen.findByText("archived")).toBeTruthy();
  });

  it("reads project projections and hook policy, and scopes subscription tests and delivery retries", async () => {
    const user = userEvent.setup();
    const calls: [string, unknown][] = [];
    open(projectPath, (url, init) => {
      if (url.pathname === "/api/v1/me") return Response.json({ ...testIdentity, permissions_by_scope: {
        p1: ["integration.read", "hook.manage"], w1: ["integration.read", "hook.manage"],
      } });
      if (init.method === "POST") {
        calls.push([url.pathname, JSON.parse(String(init.body))]);
        return Response.json({});
      }
      if (url.pathname.endsWith("/projections")) return Response.json({ next_cursor: null, items: [
        { projection_id: "pj", checkout_binding_id: "b", state: "in_sync", target: "codex" },
      ] });
      if (url.pathname.endsWith("/desired-projection")) {
        expect(url.searchParams.get("target")).toBe("codex");
        expect(url.searchParams.get("checkout_binding_id")).toBe("b");
        return Response.json({ generation: 12 });
      }
      if (url.pathname.endsWith("/hook-policy")) return Response.json({ target: url.searchParams.get("target") });
      if (url.pathname.endsWith("/hook-subscriptions")) {
        expect(url.searchParams.get("project_id")).toBe("p1");
        return Response.json({ items: [{ id: "docs", target_summary: "Docs", execution_location: "control_plane" }] });
      }
      if (url.pathname.endsWith("/hook-deliveries")) return Response.json({ next_cursor: null, items: [
        { delivery_id: "d1", subscription_id: "docs", state: "dead" },
      ] });
    });
    await user.click(await screen.findByRole("tab", { name: "Integrations" }));
    await user.click(await screen.findByRole("button", { name: "Показать конфигурацию" }));
    await screen.findByText(/"generation": 12/);
    await user.click(screen.getByRole("button", { name: "Тест подписки" }));
    await user.click(await screen.findByRole("button", { name: "Повторить доставку" }));
    await waitFor(() => expect(calls).toEqual([
      ["/api/v1/workspaces/w1/hook-subscriptions/docs/test", { project_id: "p1" }],
      ["/api/v1/workspaces/w1/hook-deliveries/retry", { delivery_ids: ["d1"] }],
    ]));
  });

  it("pages hosts in the workspace and registers a host at instance scope", async () => {
    const user = userEvent.setup();
    let created = false;
    open(workspacePath, (url, init) => {
      if (url.pathname !== "/api/v1/hosts") return;
      if (init.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({ name: "node", platform: { os: "linux", arch: "x86_64" } });
        created = true;
        return Response.json({ host_id: "h1" });
      }
      expect(url.searchParams.get("workspace_id")).toBe("w1");
      const last = url.searchParams.get("after") === "h+";
      return Response.json({ items: [{ host_id: "h1", name: last ? "last" : created ? "node" : "first", platform: { os: "linux", arch: "arm64" }, state: "active" }], next: last ? null : "h+" });
    });
    await user.click(await screen.findByRole("tab", { name: "Хосты" }));
    await user.click(await screen.findByRole("button", { name: "Далее" }));
    await screen.findByRole("cell", { name: "last" });
    await user.click(screen.getByRole("button", { name: "Назад" }));
    await user.type(screen.getByRole("textbox", { name: "Имя хоста" }), "node");
    await user.click(screen.getByRole("button", { name: "Зарегистрировать хост" }));
    await screen.findByRole("cell", { name: "node" });
  });
});
