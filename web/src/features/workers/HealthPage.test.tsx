// @vitest-environment jsdom
import "../../../tests/setup";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { AppRoutes } from "../../app/App";
import { AuthProvider } from "../../app/providers/AuthProvider";

const secret = "once-only-worker-secret";
const locator = "/private/hosts/worker.sock";
const worker = { worker_id: "w1", host_id: "h1", display_name: "Runner", state: "online", row_version: 7,
  last_heartbeat_at: null, capabilities: { isolation_profiles: ["container"] } };
const host = { host_id: "h1", name: "Test host", state: "active", registered_at: "2026-01-01T00:00:00Z", platform: { os: "linux", arch: "x86_64" } };
const diagnostic = { id: "storage.schema", status: "warn", message: "Database probe", hint: null };
const problem = () => Response.json({ code: "FORBIDDEN", category: "forbidden", detail: secret,
  details: { locator }, request_id: "req-health" }, { status: 403, headers: { "Content-Type": "application/problem+json" } });

function open(path: string, permissions: string[], handle?: (url: URL, init: RequestInit) => Response | undefined) {
  const calls: { url: URL; init: RequestInit }[] = [];
  stubFetch(async (input, init = {}) => {
    const url = new URL(String(input), location.origin);
    calls.push({ url, init });
    const result = handle?.(url, init);
    if (result) return result;
    switch (url.pathname) {
      case "/api/v1/me": return Response.json({ ...testIdentity, effective_permissions: permissions });
      case "/api/v1/config/effective": return Response.json({ keys: [] });
      case "/health/live": return Response.json({ status: "live", credentials: secret });
      case "/health/ready": return Response.json({ status: "not_ready", checks: {
        database: "ok", schema: "not_migrated", background: "fail", host_locator: locator,
      } }, { status: 503 });
      case "/health/details":
      case "/api/v1/doctor": return Response.json({ checks: [diagnostic] });
      case "/api/v1/admin/migrations": return Response.json({ state: "not_migrated", known_version: 2, db_version: 1,
        migrations: [{ version: 2, name: "add_workers", state: "pending" }] });
      case "/api/v1/admin/outbox/dead": return Response.json({ items: [{ outbox_id: "o1", event_id: "e1", destination: "queue", attempts: 3 }], next: null });
      case "/api/v1/admin/outbox/o1/retry": return Response.json({ requeued: 1 });
      case "/api/v1/workspaces/ws": return Response.json({ workspace_id: "ws", title: "Workspace" });
      case "/api/v1/workspaces/ws/workers": return init.method === "POST"
        ? Response.json({ token_secret: secret, worker_id: "new", principal_id: "p" }, { status: 201 })
        : Response.json({ items: [worker, { ...worker, worker_id: "w2", display_name: "Revoked", state: "retired" },
          { ...worker, worker_id: "w3", display_name: "Disconnected", state: "offline" }], next: null });
      case "/api/v1/workers/w1/state": return Response.json({ worker_id: "w1", state: "draining", row_version: 8 });
      case "/api/v1/hosts": return Response.json({ items: [host], next: null });
      case "/api/v1/hosts/h1": return Response.json(host);
      case "/api/v1/runtimes": return Response.json({ items: [{ runtime_id: "codex", adapter_version: "1",
        allowed_in_scope: true, registered: true, installations: [{ host_id: "h1", version: "3.1", auth_state: "expired" }] }] });
      case "/api/v1/runtimes/codex/capabilities": return Response.json({ records: [{
        capability: "sandbox_native", status: "unknown", source: "static", evidence: "not verified", limitations: "",
      }] });
      case "/api/v1/runtimes/models": return Response.json({ catalog_version: "1", stale: false, models: [{ id: "model-a" }] });
      case "/api/v1/runtimes/routing": return Response.json({ decision: { runtime_id: "codex" }, admission: {}, rejected: [] });
      default: throw new Error("Unexpected request " + url.pathname);
    }
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 30_000 } } });
  history.replaceState(null, "", path);
  render(<BrowserRouter><QueryClientProvider client={client}><AuthProvider initialToken="test-user">
    <AppRoutes />
  </AuthProvider></QueryClientProvider></BrowserRouter>);
  return { calls, client };
}

describe("Health", () => {
  it.each([200, 403])("cold-loads during SCHEMA_NOT_MIGRATED with migration response %i", async (status) => {
    sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws" }));
    const { calls } = open("/health", [], url => {
      if (url.pathname === "/api/v1/me") {
        return Response.json({ code: "SCHEMA_NOT_MIGRATED", category: "precondition", request_id: "req-schema" },
          { status: 409, headers: { "Content-Type": "application/problem+json" } });
      }
      if (url.pathname === "/api/v1/admin/migrations" && status === 403) return problem();
      return undefined;
    });

    expect(await screen.findByText("live")).toBeTruthy();
    expect(await screen.findByText("not_ready")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Состояние системы" })).toBeTruthy();
    if (status === 200) {
      expect(await screen.findByRole("cell", { name: "add_workers" })).toBeTruthy();
      expect(screen.getByRole("cell", { name: "pending" })).toBeTruthy();
    } else {
      expect(within(await screen.findByRole("alert")).getByText("FORBIDDEN")).toBeTruthy();
      expect(screen.queryByRole("cell", { name: "add_workers" })).toBeNull();
    }

    expect(calls.map(({ url }) => url.pathname).sort()).toEqual([
      "/api/v1/admin/migrations", "/api/v1/me", "/health/live", "/health/ready",
    ]);
    const migration = calls.find(({ url }) => url.pathname === "/api/v1/admin/migrations");
    expect(migration?.init.method).toBe("GET");
    expect(new Headers(migration?.init.headers).get("Authorization")).toBe("Bearer test-user");
  });

  it("polls public checks every 15 seconds without credentials and allowlists the degraded response", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    try {
      const { calls, client } = open("/health", []);
      await screen.findByText("not_migrated", {}, { timeout: 5000 });
      expect(screen.getByText("not_ready")).toBeTruthy();
      expect(screen.getByText("fail")).toBeTruthy();
      const probes = () => calls.filter(c => c.url.pathname.startsWith("/health/"));
      expect(probes()).toHaveLength(2);
      await act(async () => { await vi.advanceTimersByTimeAsync(14_999); });
      expect(probes()).toHaveLength(2);
      await act(async () => { await vi.advanceTimersByTimeAsync(1); });
      await waitFor(() => expect(probes()).toHaveLength(4));
      expect(probes().every(c => !new Headers(c.init.headers).has("Authorization"))).toBe(true);
      expect(calls.some(c => /doctor|details|admin/u.test(c.url.pathname))).toBe(false);
      for (const value of [secret, locator]) {
        expect(document.body.textContent).not.toContain(value);
        expect(JSON.stringify(client.getQueriesData({ queryKey: ["health"] }))).not.toContain(value);
      }
    } finally { vi.useRealTimers(); }
  });

  it("reads migrations when readiness is degraded and diagnostic routes are forbidden", async () => {
    const { calls } = open("/health", ["admin.storage"]);
    await screen.findByRole("cell", { name: "add_workers" });
    expect(screen.getByRole("cell", { name: "pending" })).toBeTruthy();
    expect(await screen.findByText("not_ready")).toBeTruthy();
    expect(calls.filter(c => /doctor|details|outbox/u.test(c.url.pathname))).toEqual([]);
    expect(calls.filter(c => c.url.pathname.endsWith("/migrations")).map(c => c.init.method)).toEqual(["GET"]);
  });

  it("keeps migration status available when the diagnostic API reports SCHEMA_NOT_MIGRATED", async () => {
    open("/health", ["config.read", "admin.storage"], url => {
      if (!["/health/details", "/api/v1/doctor"].includes(url.pathname)) return undefined;
      return Response.json({ code: "SCHEMA_NOT_MIGRATED", category: "precondition", request_id: "req-schema" },
        { status: 503, headers: { "Content-Type": "application/problem+json" } });
    });
    expect(await screen.findByRole("cell", { name: "pending" })).toBeTruthy();
    await waitFor(() => expect(screen.getAllByText("SCHEMA_NOT_MIGRATED")).toHaveLength(2));
  });

  it("filters Doctor checks and retries a dead outbox event", async () => {
    const { calls } = open("/health", ["config.read", "admin.events"]);
    await screen.findByRole("heading", { name: "Doctor" });
    await waitFor(() => expect(screen.getAllByRole("cell", { name: "Database probe" })).toHaveLength(2));
    await userEvent.type(screen.getByRole("textbox", { name: "Коды проверок через запятую" }), "storage.schema");
    await userEvent.click(screen.getByRole("button", { name: "Применить фильтр" }));
    await waitFor(() => expect(calls.some(c => c.url.searchParams.get("only") === "storage.schema")).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "Повторить доставку" }));
    await screen.findByText(/Возвращено в очередь/u);
    const retry = calls.find(c => c.init.method === "POST");
    expect(retry?.url.pathname).toBe("/api/v1/admin/outbox/o1/retry");
    expect(new Headers(retry?.init.headers).has("Idempotency-Key")).toBe(true);
    expect(screen.queryByRole("heading", { name: "Миграции" })).toBeNull();
  });

  it("renders the Problem code and request ID without server echoes", async () => {
    open("/health", ["config.read"], url => url.pathname === "/health/details" ? problem() : undefined);
    const alert = within(await screen.findByRole("alert"));
    expect(alert.getByText("FORBIDDEN")).toBeTruthy();
    expect(alert.getByText("req-health")).toBeTruthy();
    expect(document.body.textContent).not.toContain(locator);
    expect(document.body.textContent).not.toContain(secret);
  });
});

describe("Workers and runtimes", () => {
  it("uses If-Match and legal state transitions, and fetches the selected host", async () => {
    const { calls } = open("/workers?workspace_id=ws", ["workspace.read", "worker.register"]);
    const revoked = within(await screen.findByRole("row", { name: /Revoked/u }));
    expect(revoked.getByRole("cell", { name: "retired · неактивен" })).toBeTruthy();
    expect(revoked.queryByRole("button", { name: /^(online|offline|draining|retired)$/u })).toBeNull();
    expect(screen.getByRole("cell", { name: "offline · неактивен" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "offline" })).toBeNull();
    await userEvent.click(within(screen.getByRole("row", { name: /Runner/u })).getByRole("button", { name: "draining" }));
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Подтвердить" }));
    await waitFor(() => expect(calls.some(c => c.url.pathname.endsWith("/w1/state"))).toBe(true));
    const state = calls.find(c => c.url.pathname.endsWith("/w1/state"))!;
    expect(new Headers(state.init.headers).get("If-Match")).toBe('W/"v7"');
    expect(JSON.parse(String(state.init.body))).toEqual({ state: "draining" });
    await userEvent.click(screen.getByRole("button", { name: "Test host" }));
    await screen.findByRole("heading", { name: "Test host" });
    expect(calls.some(c => c.url.pathname === "/api/v1/hosts" && c.url.searchParams.get("workspace_id") === "ws")).toBe(true);
  });

  it("registers without an idempotency key and discards the one-time token on dismissal", async () => {
    const { calls, client } = open("/workers?workspace_id=ws", ["worker.register"]);
    for (const [name, value] of [["Имя воркера", "Registered"], ["ID хоста", "h1"], ["Версия SKM", "2.0.0"],
      ["Профили изоляции через запятую", "worktree"]] as const) {
      await userEvent.type(await screen.findByRole("textbox", { name }), value);
    }
    await userEvent.click(screen.getByRole("button", { name: "Зарегистрировать воркера" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Одноразовый токен воркера" }));
    expect(dialog.getByText(secret)).toBeTruthy();
    const posts = calls.filter(c => c.init.method === "POST");
    expect(posts).toHaveLength(1);
    expect(new Headers(posts[0]?.init.headers).has("Idempotency-Key")).toBe(false);
    expect(JSON.parse(String(posts[0]?.init.body))).toMatchObject({ host_id: "h1", display_name: "Registered", capabilities: { skm_version: "2.0.0" } });
    expect(JSON.stringify(client.getQueriesData({}))).not.toContain(secret);
    expect(client.getMutationCache().getAll()).toHaveLength(0);
    await userEvent.click(dialog.getByRole("button", { name: "Закрыть" }));
    expect(document.body.textContent).not.toContain(secret);
    expect(JSON.stringify([sessionStorage, localStorage])).not.toContain(secret);
  });

  it("reads version-specific capabilities, models and routing without promoting unknown", async () => {
    const { calls } = open("/runtimes", ["runtime.read"]);
    await userEvent.click(await screen.findByRole("button", { name: "h1 · 3.1" }));
    const capability = within(await screen.findByRole("row", { name: /sandbox_native/u }));
    expect(capability.getByText("unknown").getAttribute("data-tone")).toBe("neutral");
    expect(calls.some(c => c.url.pathname.endsWith("/capabilities") && c.url.searchParams.get("runtime_version") === "3.1")).toBe(true);
    expect(calls.some(c => c.url.pathname.endsWith("/models") && c.url.searchParams.get("runtime_id") === "codex")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Объяснить выбор" }));
    await waitFor(() => expect(calls.some(c => c.url.pathname.endsWith("/routing") &&
      c.url.searchParams.get("role") === "executor" && c.url.searchParams.get("scope") === "instance")).toBe(true));
  });

  it("displays an unavailable backend separately from missing installations", async () => {
    open("/runtimes", ["runtime.read"], url => {
      if (url.pathname === "/api/v1/runtimes") throw new TypeError("network");
      return undefined;
    });
    expect(within(await screen.findByRole("alert")).getByText("BACKEND_UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByText("Установка не обнаружена")).toBeNull();
  });
});
