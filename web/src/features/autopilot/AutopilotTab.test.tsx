// @vitest-environment jsdom
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import "../../../tests/setup";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { App } from "../../app/App";

const base = "/api/v1/projects/project-a/autopilot";
const enabledKey = "execution.autopilot.enabled";
const config = "/api/v1/config/entries/project:project-a/" + enabledKey;
const status = {
  effective_state: "paused", state: "paused", emergency: false, current_run_id: "run-a",
  queue: [{ alias: "PLAN7", status: "ready" }], counters: { runs_started: 12 },
  stop_code: "AUTOPILOT_OWNER_NEEDED", stop_detail: "<img>\u202eпричина", session_started_at: "2026-01-01",
};
const reason = "Оператор проверил очередь";

function open(options: {
  permissions?: string[]; state?: string; enabled?: boolean; write?: (index: number) => Response;
} = {}) {
  let enabled = options.enabled ?? true;
  let version: number | null = enabled ? 5 : null;
  let count = 12;
  let cursor = 14;
  let staleSnapshots = new Set<string>();
  let statusUnavailable = false;
  let retryPermissions = options.permissions ?? ["run.control", "config.write"];
  const writes: { path: string; method: string; headers: Headers; body: Record<string, unknown> }[] = [];
  const streams: ReadableStreamDefaultController<Uint8Array>[] = [];
  const fetch = stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    const path = decodeURIComponent(url.pathname);
    const method = init?.method ?? "GET";
    if (["POST", "PUT"].includes(method)) {
      const body = JSON.parse(String(init?.body));
      writes.push({ path, body, method, headers: new Headers(init?.headers) });
      if (options.write) return options.write(writes.length);
      if (path === config) { enabled = body.value; version = (version ?? 0) + 1; }
      return Response.json({});
    }
    switch (path) {
      case "/api/v1/me": return Response.json({ ...testIdentity,
        effective_permissions: url.searchParams.has("scope_id") ? retryPermissions : ["run.control"],
        permissions_by_scope: { "project-a": options.permissions ?? ["run.control", "config.write"] } });
      case "/api/v1/workspaces/ws-a": return Response.json({ workspace_id: "ws-a", title: "Пространство" },
        { headers: { "SKM-Events-Cursor": String(cursor) } });
      case base: return statusUnavailable ? Response.json({
        code: "NOT_FOUND", category: "not_found", request_id: "status-refresh-error",
      }, { status: 404, headers: { "Content-Type": "application/problem+json" } })
        : Response.json({ ...status, state: options.state ?? status.state, counters: { runs_started: count } },
          { headers: { "SKM-Events-Cursor": String(staleSnapshots.delete(path) ? 14 : cursor) } });
      case base + "/explain": return Response.json({
        status: { nearest_limit: { id: "AP5" } }, keys: [{ key: enabledKey, value: enabled, provenance: "project" }],
        stop_conditions: [{ id: "AP1", code: "AUTOPILOT_NO_WORK" }], next_plan: { alias: "PLAN8" },
      }, { headers: { "SKM-Events-Cursor": String(staleSnapshots.delete(path) ? 14 : cursor) } });
      case "/api/v1/config/entries": return Response.json({
        items: version === null ? [] : [{ key: enabledKey, row_version: version }], next: null,
      });
      case "/api/v1/events": return streams.length ? new Response(null, { status: 429 }) : new Response(new ReadableStream({
        start(controller) { streams.push(controller); },
      }), { headers: { "Content-Type": "text/event-stream" } });
      default: return new Response(null, { status: 404 });
    }
  });
  history.replaceState(null, "", "/p/project-a/autopilot?workspace_id=ws-a");
  render(<App initialToken="operator" />);
  async function emit(seq: number, type: string, stream_kind: string, stream_id: string, payload: object) {
    cursor = seq;
    await waitFor(() => expect(streams).toHaveLength(1));
    const event = { type, workspace_id: "ws-a", stream_kind, stream_id, payload };
    await act(async () => streams[0]!.enqueue(new TextEncoder().encode(
      `id: ${seq}\nevent: message\ndata: ${JSON.stringify(event)}\n\n`,
    )));
  }
  return {
    writes, fetch,
    reads: (path: string) => fetch.mock.calls.filter(([url, init]) => String(url) === path && init?.method === "GET").length,
    emitRun(seq: number, type: string, project: string, nextCount: number) {
      count = nextCount;
      return emit(seq, type, "run", "run-a", { project_id: project, run_id: "run-a" });
    },
    emitState(seq: number, nextCount: number) {
      count = nextCount;
      return emit(seq, "AutopilotStateChanged", "project", "project-a", {});
    },
    emitConfig(seq: number, level: string, id: string, nextEnabled: boolean) {
      enabled = nextEnabled;
      return emit(seq, "urn:skm:settings:event:config-changed:v1", "config", id,
        { scope: { level, scope_id: id }, keys: [enabledKey] });
    },
    returnStaleSnapshots() { staleSnapshots = new Set([base, base + "/explain"]); },
    failStatusRefresh() { statusUnavailable = true; },
    revokeRetryPermissions() { retryPermissions = []; },
  };
}

async function confirm(name: string) {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name }));
  const dialog = within(await screen.findByRole("alertdialog", { name }));
  await user.type(dialog.getByRole("textbox", { name: "Причина" }), reason);
  await user.click(dialog.getByRole("button", { name: "Подтвердить" }));
}

describe("AutopilotTab", () => {
  it("uses one workspace feed and rereads both Autopilot snapshots when the stream cursor is ahead", async () => {
    const app = open({ permissions: [] });
    expect(await screen.findByRole("heading", { name: "Состояние автопилота" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "run-a" }).getAttribute("href")).toBe("/runs/run-a?project_id=project-a");
    expect(screen.getByText("<img>\\u202eпричина")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText("PLAN7")).toBeTruthy();
    expect(await screen.findByText("PLAN8")).toBeTruthy();
    expect(screen.getByText(/AP1 AUTOPILOT_NO_WORK/u)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Экстренная остановка" })).toBeNull();
    const statusReads = app.reads(base);
    const explainReads = app.reads(base + "/explain");
    await app.emitRun(16, "RunStarted", "other-project", 44);
    expect(app.reads(base)).toBe(statusReads);
    app.returnStaleSnapshots();
    await app.emitRun(17, "urn:skm:execution:event:run-finished:v1", "project-a", 45);
    expect(await screen.findByText("45")).toBeTruthy();
    expect(app.reads(base)).toBe(statusReads + 2);
    expect(app.reads(base + "/explain")).toBe(explainReads + 2);
    await app.emitState(18, 46);
    expect(await screen.findByText("46")).toBeTruthy();
    expect(app.fetch.mock.calls.filter(([url]) => String(url).startsWith("/api/v1/events?"))).toHaveLength(1);
    expect(app.writes).toHaveLength(0);
  });

  it.each([["project", "project-a"], ["workspace", "ws-a"]])(
    "refreshes status and explain when the enabled setting changes at %s scope", async (level, id) => {
      const app = open();
      await screen.findByRole("button", { name: "Выключить" });
      const statusReads = app.reads(base);
      const explainReads = app.reads(base + "/explain");
      await app.emitConfig(15, "project", "other-project", true);
      expect(app.reads(base)).toBe(statusReads);
      expect(app.reads(base + "/explain")).toBe(explainReads);
      await app.emitConfig(16, level, id, false);
      await screen.findByRole("button", { name: "Включить" });
      expect(app.reads(base)).toBeGreaterThan(statusReads);
      expect(app.reads(base + "/explain")).toBeGreaterThan(explainReads);
    },
  );

  it.each(["paused", "stopped"])("continues %s with the existing session and explicitly resets only on request", async state => {
    const app = open({ state });
    await confirm("Продолжить");
    expect(app.writes[0]).toMatchObject({ path: base + "/start", body: { reason, new_session: false } });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Новая сессия" }));
    const dialog = within(await screen.findByRole("alertdialog", { name: "Новая сессия" }));
    await user.click(dialog.getByRole("button", { name: "Подтвердить" }));
    expect(app.writes).toHaveLength(1);
    await user.type(dialog.getByRole("textbox", { name: "Причина" }), reason);
    await user.click(dialog.getByRole("button", { name: "Подтвердить" }));
    expect(app.writes[1]).toMatchObject({ path: base + "/start", body: { reason, new_session: true } });
  });

  it("separates pause, drain, normal stop and confirmed emergency stop", async () => {
    const app = open();
    await confirm("Приостановить");
    await confirm("Завершить после текущего запуска");
    await confirm("Остановить");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Экстренная остановка" }));
    const dialog = within(await screen.findByRole("alertdialog", { name: "Экстренная остановка" }));
    await user.click(dialog.getByRole("button", { name: "Подтвердить" }));
    await user.click(dialog.getByRole("button", { name: "Отмена" }));
    expect(app.writes).toHaveLength(3);
    await confirm("Экстренная остановка");
    expect(app.writes.map(({ path, body }) => [path, body])).toEqual([
      [base + "/pause", { reason }], [base + "/drain", { reason }],
      [base + "/stop", { reason, emergency: false }], [base + "/stop", { reason, emergency: true }],
    ]);
  });

  it("creates and then updates the project config entry using its write precondition", async () => {
    const app = open({ enabled: false, permissions: ["config.write"] });
    await confirm("Включить");
    await confirm("Выключить");
    expect(app.writes.map(({ path, method, body }) => [path, method, body.value])).toEqual([
      [config, "PUT", true], [config, "PUT", false],
    ]);
    expect(app.writes[0]?.headers.get("If-None-Match")).toBe("*");
    expect(app.writes[1]?.headers.get("If-Match")).toBe('W/"v1"');
    expect(screen.queryByRole("button", { name: "Экстренная остановка" })).toBeNull();
  });

  it("shows AUTOPILOT_NOT_ENABLED and its request ID", async () => {
    const app = open({ state: "idle", write: () => Response.json({
      code: "AUTOPILOT_NOT_ENABLED", category: "precondition", request_id: "ap-409",
    }, { status: 409, headers: { "Content-Type": "application/problem+json" } }) });
    await confirm("Запустить");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("AUTOPILOT_NOT_ENABLED");
    expect(alert.textContent).toContain("ap-409");
    expect(app.writes).toHaveLength(1);
  });

  it("preserves the same request and idempotency key when the status refresh also fails", async () => {
    const app = open({ write: index => {
      if (index === 1) throw new TypeError("connection interrupted");
      return Response.json({});
    } });
    await screen.findByRole("button", { name: "Продолжить" });
    app.failStatusRefresh();
    await confirm("Продолжить");
    await screen.findByText("status-refresh-error");
    const commandError = (await screen.findAllByRole("alert")).find(alert => alert.textContent?.includes("BACKEND_UNAVAILABLE"));
    expect(commandError).toBeDefined();
    expect(app.writes).toHaveLength(1);
    const user = userEvent.setup();
    await user.click(within(commandError!).getByRole("button", { name: "Повторить" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Повторить запрос" }));
    await waitFor(() => expect(app.writes).toHaveLength(2));
    const key = app.writes[0]?.headers.get("Idempotency-Key");
    expect(key).toMatch(/^web-/u);
    expect(app.writes[1]?.headers.get("Idempotency-Key")).toBe(key);
    expect(app.writes[1]?.body).toEqual(app.writes[0]?.body);
    expect(app.reads("/api/v1/me?scope_id=project-a")).toBe(1);
  });

  it("checks current project permissions before resending a command", async () => {
    const app = open({ write: () => { throw new TypeError("connection interrupted"); } });
    await confirm("Экстренная остановка");
    const error = await screen.findByRole("alert");
    const user = userEvent.setup();
    await user.click(within(error).getByRole("button", { name: "Повторить" }));
    app.revokeRetryPermissions();
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Повторить запрос" }));
    expect(await screen.findByText("FORBIDDEN", { selector: "code" })).toBeTruthy();
    expect(app.reads("/api/v1/me?scope_id=project-a")).toBe(1);
    expect(app.writes).toHaveLength(1);
  });
});
