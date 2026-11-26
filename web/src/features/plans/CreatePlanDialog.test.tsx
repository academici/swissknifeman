import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { App } from "../../app/App";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";

it.each(["feature", "blank", "retry"])("creates a %s plan and opens its draft", async (mode) => {
  const writes: { path: string; body: unknown; key: string | null }[] = [];
  const reads: URL[] = [];
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    reads.push(url);
    if (init?.method === "POST") {
      writes.push({ path: url.pathname, body: JSON.parse(String(init.body)), key: new Headers(init.headers).get("Idempotency-Key") });
      if (mode === "retry" && writes.length === 1) throw new TypeError("Response lost");
      return Response.json({ plan_id: "plan", alias: "PLAN1", draft_id: mode === "feature" || url.pathname.endsWith("/drafts") ? "draft" : null });
    }
    switch (url.pathname) {
      case "/api/v1/me": return Response.json({ ...testIdentity, permissions_by_scope: { project: ["plan.create"] } });
      case "/api/v1/projects/project": return Response.json({ workspace_id: "ws" });
      case "/api/v1/workspaces/ws": return Response.json({ workspace_id: "ws" });
      case "/api/v1/projects/project/plans": return Response.json({
        items: [{ plan_id: "review", purpose: "review_requests", alias: "SERVICE", title: "Review" }], next_cursor: null,
      });
      case "/api/v1/extensions/resources": return Response.json({ items: [{ key: "feature", kind: "plan_template", quarantined: false }], next_cursor: null });
      case "/api/v1/extensions/resolve": return Response.json({ chosen: { kind: "plan_template", key: "feature", manifest: {
        inputs_schema: { type: "object", additionalProperties: false, properties: { goal: { type: "string" } } },
      } } });
      default: throw new Error(url.pathname);
    }
  });
  history.replaceState(null, "", "/p/project/plans");
  render(<App initialToken="test" />);
  await screen.findByRole("heading", { name: "Планов нет" }, { timeout: 5000 });
  expect(screen.queryByRole("link", { name: "SERVICE" })).toBeNull();
  expect(reads.find((u) => u.pathname.endsWith("/plans"))?.searchParams.get("purpose")).toBe("standard");
  await userEvent.click(screen.getByRole("button", { name: "Создать план" }));
  const dialog = within(await screen.findByRole("dialog", { name: "Создать план" }));
  await userEvent.type(dialog.getByRole("textbox", { name: "Название плана" }), "New plan");
  if (mode === "feature") {
    await userEvent.selectOptions(dialog.getByRole("combobox", { name: "Шаблон" }), (await dialog.findByRole("option", { name: "feature" })));
    await userEvent.type(await dialog.findByRole("textbox", { name: "goal" }), "Ship");
  }
  await userEvent.click(dialog.getByRole("button", { name: "Создать" }));
  if (mode === "retry") {
    await dialog.findByRole("alert");
    expect(writes).toHaveLength(1);
    await userEvent.click(dialog.getByRole("button", { name: "Создать" }));
    expect(writes[0]?.key).toBe(writes[1]?.key);
  }
  await screen.findByRole("heading", { name: "Редактор черновика" });
  expect(location.pathname).toBe("/plans/plan/drafts/draft");
  expect(writes.slice(mode === "retry" ? 1 : 0).map((w) => w.body)).toEqual(mode === "feature"
    ? [{ title: "New plan", template_key: "feature", template_inputs: { goal: "Ship" } }]
    : [{ title: "New plan" }, { base: "empty" }]);
  expect(writes.every((w) => w.key?.startsWith("web-"))).toBe(true);
});

it.each(["create", "draft"])("reloads the affected resource after a %s conflict", async (stage) => {
  const projectPath = "/api/v1/projects/project";
  const planPath = "/api/v1/plans/plan";
  const reads: string[] = [];
  const writes: string[] = [];
  stubFetch(async (input, init) => {
    const { pathname } = new URL(String(input), location.origin);
    if (init?.method === "POST") {
      writes.push(pathname);
      if (stage === "draft" && pathname === projectPath + "/plans") {
        return Response.json({ plan_id: "plan", alias: "PLAN1", draft_id: null });
      }
      return Response.json({ code: "PROJECT_ARCHIVED", category: "conflict", details: { project_id: "project" } },
        { status: 409, headers: { "Content-Type": "application/problem+json" } });
    }
    reads.push(pathname);
    switch (pathname) {
      case "/api/v1/me": return Response.json({ ...testIdentity, permissions_by_scope: { project: ["plan.create"] } });
      case "/api/v1/workspaces/ws": return Response.json({});
      case projectPath: return Response.json({ project_id: "project", workspace_id: "ws", state: "archived" });
      case projectPath + "/plans": return Response.json({ items: [], next_cursor: null });
      case planPath: return Response.json({ plan_id: "plan", project_id: "project", workspace_id: "ws", lifecycle_state: "active" });
      case "/api/v1/extensions/resources": return Response.json({
        items: [{ key: "feature", kind: "plan_template", quarantined: false }], next_cursor: null,
      });
      case "/api/v1/extensions/resolve": return Response.json({ chosen: { kind: "plan_template", key: "feature", manifest: {
        inputs_schema: { type: "object", properties: { goal: { type: "string" } } },
      } } });
      default: throw new Error(pathname);
    }
  });
  sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws", projectId: "project" }));
  history.replaceState(null, "", "/p/project/plans");
  render(<App initialToken="test" />);
  await userEvent.click(await screen.findByRole("button", { name: "Создать план" }));
  const dialog = within(await screen.findByRole("dialog", { name: "Создать план" }));
  await userEvent.type(dialog.getByRole("textbox", { name: "Название плана" }), "New plan");
  if (stage === "create") {
    await userEvent.selectOptions(dialog.getByRole("combobox", { name: "Шаблон" }), await dialog.findByRole("option", { name: "feature" }));
    await userEvent.type(await dialog.findByRole("textbox", { name: "goal" }), "Ship");
  }
  await userEvent.click(dialog.getByRole("button", { name: "Создать" }));
  const panel = within(await dialog.findByRole("alert"));
  expect(panel.getByRole("heading", { name: "Конфликт изменений" })).toBeTruthy();
  const expectedPath = stage === "create" ? projectPath : planPath;
  expect(reads).not.toContain(expectedPath);
  await userEvent.click(panel.getByRole("button", { name: "Загрузить текущую версию" }));
  await waitFor(() => expect(dialog.queryByRole("alert")).toBeNull());
  expect(reads.filter((path) => path === expectedPath)).toHaveLength(1);
  if (stage === "create") {
    expect(dialog.getByRole<HTMLInputElement>("textbox", { name: "Название плана" }).value).toBe("New plan");
    expect(dialog.getByRole<HTMLSelectElement>("combobox", { name: "Шаблон" }).value).toBe("feature");
    expect(dialog.getByRole<HTMLInputElement>("textbox", { name: "goal" }).value).toBe("Ship");
    expect(writes).toEqual([projectPath + "/plans"]);
  } else {
    expect(await dialog.findByRole("button", { name: "Открыть черновик" })).toBeTruthy();
    expect(dialog.getByRole("link", { name: "PLAN1" }).getAttribute("href")).toBe("/plans/plan");
    expect(writes).toEqual([projectPath + "/plans", planPath + "/drafts"]);
  }
});

it("resets the cursor on a state change and gates creation on project permissions", async () => {
  const reads: URL[] = [];
  stubFetch(async (input) => {
    const url = new URL(String(input), location.origin);
    if (url.pathname === "/api/v1/me") return Response.json({ ...testIdentity, permissions_by_scope: { project: ["plan.read"] } });
    if (url.pathname === "/api/v1/projects/project") return Response.json({ workspace_id: null });
    if (url.pathname !== "/api/v1/projects/project/plans") throw new Error(url.pathname);
    reads.push(url);
    const archived = url.searchParams.get("state") === "archived";
    const second = url.searchParams.has("after");
    const alias = archived ? "OLD" : second ? "NEXT" : "FIRST";
    return Response.json({ items: [{
      alias, plan_id: alias, title: alias, purpose: "standard", lifecycle_state: archived ? "archived" : "active",
      updated_at: "2026-01-01", current_revision_no: null, open_drafts: 0,
    }], next_cursor: archived || second ? null : "cursor/2" });
  });
  history.replaceState(null, "", "/p/project/plans");
  render(<App initialToken="test" />);
  await screen.findByRole("link", { name: "FIRST" });
  expect(screen.queryByRole("button", { name: "Создать план" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Далее" }));
  await screen.findByRole("link", { name: "NEXT" });
  expect(reads.at(-1)?.searchParams.get("after")).toBe("cursor/2");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Состояние" }), "archived");
  await screen.findByRole("link", { name: "OLD" });
  expect(reads.at(-1)?.searchParams.has("after")).toBe(false);
  expect(screen.queryByRole("button", { name: "Назад" })).toBeNull();
});
