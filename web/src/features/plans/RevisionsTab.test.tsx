import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { App } from "../../app/App";

function openPlan({ archiveGate, refreshGate, openDraftConflict = false }: {
  archiveGate?: Promise<void>;
  refreshGate?: Promise<void>;
  openDraftConflict?: boolean;
} = {}) {
  const writes: { path: string; init: RequestInit | undefined }[] = [];
  let archived = false;
  let restored = false;
  stubFetch(async (input, init) => {
    const path = new URL(String(input), location.origin).pathname;
    if (init?.method === "POST") {
      writes.push({ path, init });
      if (path.endsWith("/archive")) {
        await archiveGate;
        archived = true;
        return Response.json({ plan_id: "p", lifecycle_state: "archived", row_version: 10, changed: true, abandoned_draft_ids: ["draft"] });
      }
      if (path.endsWith("/drafts") && openDraftConflict) {
        archived = true;
        return Response.json({ code: "PLAN_ARCHIVED", category: "conflict", details: { plan_id: "p" } },
          { status: 409, headers: { "Content-Type": "application/problem+json" } });
      }
      restored = true;
      return Response.json({ revision_id: "restored", revision_no: 3, plan_id: "p" });
    }
    if (path === "/api/v1/me") return Response.json({ ...testIdentity, permissions_by_scope: { p: ["plan.publish", "plan.archive", "plan.edit"] } });
    if (path === "/api/v1/plans/p") {
      if (archived) await refreshGate;
      return Response.json({
        plan_id: "p", alias: "PLAN1", title: "Title", open_drafts: archived ? 0 : 1, lifecycle_state: archived ? "archived" : "active",
        current_revision_id: restored ? "restored" : "head", current_revision_no: restored ? 3 : 2, row_version: archived ? 10 : 9,
      });
    }
    if (path.endsWith("/revisions")) return Response.json({ items: [{
      revision_id: "old", revision_no: 1, change_reason: "Initial version", content_digest: "digest",
      origin: "draft", published_at: "2026-01-01", parent_revision_id: null, restored_from_revision_no: null,
    }], next_cursor: null });
    if (path.endsWith("/entities")) return Response.json({ items: [], next_cursor: null });
    if (path.includes("/revisions/")) return Response.json({ tree: { phases: [] } });
    throw new Error(path);
  });
  history.replaceState(null, "", "/plans/p");
  render(<App initialToken="test" />);
  return writes;
}

it("restores the chosen revision with the displayed head and a required reason and links the new revision", async () => {
  const writes = openPlan();
  await userEvent.click(await screen.findByRole("tab", { name: "Ревизии" }, { timeout: 5000 }));
  await userEvent.click(await screen.findByRole("button", { name: "Восстановить" }));
  const dialog = within(await screen.findByRole("alertdialog", { name: "Восстановить ревизию r1?" }));
  await userEvent.click(dialog.getByRole("button", { name: "Восстановить" }));
  expect(writes).toHaveLength(0);
  await userEvent.type(dialog.getByRole("textbox", { name: "Причина" }), "Recover original");
  await userEvent.click(dialog.getByRole("button", { name: "Восстановить" }));
  expect((await screen.findByRole("link", { name: "r3" })).getAttribute("href")).toBe("/plans/p/revisions/restored");
  expect(writes.map((w) => w.path)).toEqual(["/api/v1/plans/p/restore"]);
  expect(JSON.parse(String(writes[0]?.init?.body))).toEqual({ revision_no: 1, reason: "Recover original", expected_current_revision_id: "head" });
  expect(new Headers(writes[0]?.init?.headers).get("Idempotency-Key")).toMatch(/^web-/u);
});

it("disables plan writes during archive and applies the response before the plan refetch completes", async () => {
  let finishArchive!: () => void;
  let finishRefresh!: () => void;
  const archiveGate = new Promise<void>((resolve) => { finishArchive = resolve; });
  const refreshGate = new Promise<void>((resolve) => { finishRefresh = resolve; });
  const writes = openPlan({ archiveGate, refreshGate });
  await userEvent.click(await screen.findByRole("tab", { name: "Ревизии" }));
  await screen.findByRole("button", { name: "Восстановить" });
  await userEvent.click(await screen.findByRole("button", { name: "Архивировать" }));
  const dialog = within(await screen.findByRole("alertdialog", { name: "Архивировать план?" }));
  await userEvent.click(dialog.getByRole("button", { name: "Архивировать" }));
  expect(writes).toHaveLength(0);
  await userEvent.type(dialog.getByRole("textbox", { name: "Причина" }), "Complete");
  await userEvent.click(dialog.getByRole("button", { name: "Архивировать" }));
  expect(writes.map((w) => w.path)).toEqual(["/api/v1/plans/p/archive"]);
  expect(new Headers(writes[0]?.init?.headers).get("If-Match")).toBe('W/"v9"');
  const writeButtons = ["Открыть черновик", "Восстановить", "Архивировать"];
  await waitFor(() => {
    for (const name of writeButtons) expect(screen.getByRole<HTMLButtonElement>("button", { name }).disabled).toBe(true);
  });
  expect(screen.getByText("active")).toBeTruthy();
  finishArchive();
  await screen.findByText("archived");
  expect(screen.getByRole("tab", { name: "Черновики (0)" })).toBeTruthy();
  for (const name of writeButtons) expect(screen.getByRole<HTMLButtonElement>("button", { name }).disabled).toBe(true);
  finishRefresh();
});

it("shows an Open draft conflict and reloads the plan without changing tabs", async () => {
  const writes = openPlan({ openDraftConflict: true });
  await userEvent.click(await screen.findByRole("tab", { name: "Ревизии" }));
  await userEvent.click(screen.getByRole("button", { name: "Открыть черновик" }));
  const panel = within(await screen.findByRole("alert"));
  expect(panel.getByRole("heading", { name: "Конфликт изменений" })).toBeTruthy();
  expect(writes.map((w) => w.path)).toEqual(["/api/v1/plans/p/drafts"]);
  expect(JSON.parse(String(writes[0]?.init?.body))).toEqual({ base: "current" });
  await userEvent.click(panel.getByRole("button", { name: "Загрузить текущую версию" }));
  await screen.findByText("archived");
  expect(screen.getByRole("tab", { name: "Ревизии", selected: true })).toBeTruthy();
  expect(screen.getByRole<HTMLButtonElement>("button", { name: "Открыть черновик" }).disabled).toBe(true);
});

it("refreshes the open drafts list and count for remote draft lifecycle events", async () => {
  let version = 0;
  let cursor = 10;
  let events!: ReadableStreamDefaultController<Uint8Array>;
  stubFetch(async (input) => {
    const path = new URL(String(input), location.origin).pathname;
    const headers = { "SKM-Events-Cursor": String(cursor) };
    switch (path) {
      case "/api/v1/me": return Response.json(testIdentity);
      case "/api/v1/workspaces/ws": return Response.json({});
      case "/api/v1/events": return new Response(new ReadableStream({ start(controller) { events = controller; } }), {
        headers: { "Content-Type": "text/event-stream" },
      });
      case "/api/v1/plans/p": return Response.json({
        project_id: "project", workspace_id: "ws", plan_id: "p", alias: "PLAN1", title: "Title",
        open_drafts: version ? 1 : 0, lifecycle_state: "active", current_revision_id: null, row_version: 1,
      }, { headers });
      case "/api/v1/plans/p/revisions": return Response.json({ items: [], next_cursor: null }, { headers });
      case "/api/v1/plans/p/drafts": return Response.json({
        items: version ? [{ draft_id: "draft", edit_version: version, base_revision_no: null, stale: false }] : [],
      }, { headers });
      default: throw new Error(path);
    }
  });
  function emit(name: string, nextVersion: number) {
    version = nextVersion;
    cursor++;
    const event = { type: `urn:skm:planning:event:${name}:v1`, workspace_id: "ws", stream_kind: "plan", stream_id: "p",
      workspace_seq: cursor, payload: { plan_id: "p", draft_id: "draft" } };
    events.enqueue(new TextEncoder().encode(`id: ${cursor}\nevent: domain\ndata: ${JSON.stringify(event)}\n\n`));
  }
  sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws", projectId: "project" }));
  history.replaceState(null, "", "/plans/p");
  render(<App initialToken="test" />);
  await userEvent.click(await screen.findByRole("tab", { name: "Черновики (0)" }));
  await screen.findByText("Нет открытых черновиков");
  emit("draft-opened", 1);
  await screen.findByRole("link", { name: "draft" });
  await screen.findByRole("tab", { name: "Черновики (1)" });
  emit("draft-saved", 2);
  await screen.findByRole("cell", { name: "2" });
  emit("draft-rebased", 3);
  await screen.findByRole("cell", { name: "3" });
  emit("draft-abandoned", 0);
  await screen.findByText("Нет открытых черновиков");
  await screen.findByRole("tab", { name: "Черновики (0)" });
  expect(screen.queryByRole("link", { name: "draft" })).toBeNull();
  emit("draft-opened", 1);
  await screen.findByRole("link", { name: "draft" });
  await screen.findByRole("tab", { name: "Черновики (1)" });
  emit("plan-revision-published", 0);
  await screen.findByText("Нет открытых черновиков");
  await screen.findByRole("tab", { name: "Черновики (0)" });
});

it("keeps the confirmation bound to the displayed head when a newer revision arrives before submit", async () => {
  let head = "r2";
  let events!: ReadableStreamDefaultController<Uint8Array>;
  let submitted: unknown;
  stubFetch(async (input, init) => {
    const path = new URL(String(input), location.origin).pathname;
    if (path === "/api/v1/me") return Response.json({ ...testIdentity, permissions_by_scope: { p: ["plan.publish"] } });
    if (path === "/api/v1/workspaces/ws") return Response.json({});
    if (path === "/api/v1/events") return new Response(new ReadableStream({ start(controller) { events = controller; } }), {
      headers: { "Content-Type": "text/event-stream" },
    });
    if (path === "/api/v1/plans/p") return Response.json({
      project_id: "project", workspace_id: "ws", plan_id: "p", alias: "PLAN1", title: "Title", open_drafts: 0,
      lifecycle_state: "active", current_revision_id: head, current_revision_no: head === "r2" ? 2 : 3, row_version: 2,
    }, { headers: { "SKM-Events-Cursor": head === "r2" ? "10" : "11" } });
    if (path.endsWith("/revisions")) return Response.json({ items: [{
      revision_id: "r1", revision_no: 1, change_reason: "Initial", content_digest: "digest",
      origin: "draft", published_at: "2026-01-01", restored_from_revision_no: null,
    }], next_cursor: null });
    if (path.endsWith("/entities")) return Response.json({ items: [], next_cursor: null });
    if (path.includes("/revisions/")) return Response.json({ tree: { phases: [] } });
    if (path.endsWith("/restore")) {
      submitted = JSON.parse(String(init?.body));
      return Response.json({ code: "VERSION_CONFLICT", category: "conflict", details: { current_revision_id: head } },
        { status: 409, headers: { "Content-Type": "application/problem+json" } });
    }
    throw new Error(path);
  });
  sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws", projectId: "project" }));
  history.replaceState(null, "", "/plans/p");
  render(<App initialToken="test" />);
  await userEvent.click(await screen.findByRole("tab", { name: "Ревизии" }));
  await userEvent.click(await screen.findByRole("button", { name: "Восстановить" }));
  const dialog = within(await screen.findByRole("alertdialog"));
  head = "r3";
  const event = { type: "PlanRevisionPublished", workspace_id: "ws", stream_kind: "plan", stream_id: "p",
    workspace_seq: 11, payload: { plan_id: "p", project_id: "project" } };
  events.enqueue(new TextEncoder().encode(`id: 11\nevent: domain\ndata: ${JSON.stringify(event)}\n\n`));
  await screen.findByRole("option", { name: "r3", hidden: true });
  await userEvent.type(dialog.getByRole("textbox", { name: "Причина" }), "Restore r1");
  await userEvent.click(dialog.getByRole("button", { name: "Восстановить" }));
  await screen.findByRole("button", { name: "Загрузить текущую версию" });
  expect(submitted).toEqual({ revision_no: 1, expected_current_revision_id: "r2", reason: "Restore r1" });
});
