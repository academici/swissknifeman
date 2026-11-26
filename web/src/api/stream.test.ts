// @vitest-environment jsdom

import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import { QueryClient, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { createElement, type PropsWithChildren } from "react";
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stubFetch, testIdentity } from "../../tests/fakeTransport";
import { App } from "../app/App";
import { AuthProvider, useAuth } from "../app/providers/AuthProvider";
import { QueryProvider } from "../app/providers/QueryProvider";
import { ScopeProvider } from "../app/providers/ScopeProvider";
import { StreamProvider, useStream } from "../app/providers/StreamProvider";
import { ToastProvider } from "../app/providers/ToastProvider";
import { tokenStore } from "../features/auth/tokenStore";
import type * as Artifacts from "./generated/artifacts";
import type * as Execution from "./generated/execution";
import type { EventEnvelope, Uuid } from "./generated/kernel";
import type * as Planning from "./generated/planning";
import type * as Policy from "./generated/policy";
import type * as Settings from "./generated/settings";
import type * as Workspace from "./generated/workspace";
import { invalidateEvent } from "./invalidation";
import { keys } from "./keys";
import { EventStream, type EventStreamHandlers } from "./stream";
import { HttpTransport, type Response as ApiResponse } from "./transport";

const workspaceId = "0192f5c5-0a10-7b22-8f00-1a2b3c4d5e6f" as Uuid;
const otherWorkspace = "0192f5c5-0a10-7b22-8f00-1a2b3c4d5e70" as Uuid;
const projectId = "0192f5c5-0a10-7b22-8f00-1a2b3c4d5e71" as Uuid;
const otherProject = "0192f5c5-0a10-7b22-8f00-1a2b3c4d5e72";
const runId = "0192f5f9-8765-7af0-8f01-1a2b3c4d5e6f" as Uuid;
const scope = { workspaceId, projectId };
const scoped = keys.forScope(scope);
const token = "test-token";
const encoder = new TextEncoder();
const streams: EventStream[] = [];

function envelope(type: string, seq = 1, overrides: Partial<EventEnvelope> = {}): EventEnvelope {
  return {
    id: runId, type, schema_version: 1, stream_kind: "run", stream_id: runId,
    stream_seq: seq, workspace_id: workspaceId, workspace_seq: seq,
    correlation_id: "test", occurred_at: testIdentity.principal.created_at,
    recorded_at: testIdentity.principal.created_at, payload: { project_id: projectId },
    ...overrides,
  };
}

function frame(seq: number, type = "RunStarted", overrides?: Partial<EventEnvelope>): string {
  return `id: ${seq}\ndata: ${JSON.stringify(envelope(type, seq, overrides))}\n\n`;
}

function cursor(seq: number): string {
  return `id: ${seq}\nevent: cursor\ndata: {}\n\n`;
}

function source() {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  const cancel = vi.fn();
  const body = new ReadableStream<Uint8Array>({ start: (value) => { controller = value; }, cancel });
  return {
    response: new Response(body, { headers: { "Content-Type": "text/event-stream" } }),
    write: (text: string) => controller.enqueue(encoder.encode(text)),
    writeBytes: (text: string) => {
      for (const byte of encoder.encode(text)) controller.enqueue(Uint8Array.of(byte));
    },
    end: () => controller.close(),
    cancel,
  };
}

function problem(status: number, code: string) {
  return Response.json({ code, category: "test", detail: code }, {
    status, headers: { "Content-Type": "application/problem+json" },
  });
}

function start(fetch: typeof globalThis.fetch, handlers: Partial<EventStreamHandlers> = {}) {
  const onEvent = vi.fn();
  const stream = new EventStream({ workspaceId }, { onEvent, ...handlers }, { fetch });
  streams.push(stream);
  return { stream, onEvent };
}

function tick(ms = 0) {
  return act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

function locationFor(workspace: string, project: string): string {
  return `/p/${project}?workspace_id=${workspace}`;
}

function mount(handler: typeof fetch) {
  tokenStore.set(token);
  const fetch = stubFetch((input, init) =>
    String(input) === "/api/v1/me" ? Promise.resolve(Response.json(testIdentity)) : handler(input, init),
  );
  function Providers({ children }: PropsWithChildren) {
    return createElement(MemoryRouter, { initialEntries: [locationFor(workspaceId, projectId)] },
      createElement(QueryProvider, null,
        createElement(AuthProvider, { initialToken: token },
          createElement(ScopeProvider, null,
            createElement(ToastProvider, null,
              createElement(StreamProvider, null, children),
            ),
          ),
        ),
      ),
    );
  }
  const hook = renderHook(() => ({
    stream: useStream(),
    auth: useAuth(),
    client: useQueryClient(),
    navigate: useNavigate(),
    pathname: useLocation().pathname,
  }), { wrapper: Providers });
  const events = () => fetch.mock.calls.filter(([path]) => String(path).startsWith("/api/v1/events?"));
  return { ...hook, events };
}

beforeEach(() => {
  sessionStorage.clear();
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  for (const stream of streams.splice(0)) stream.close();
  tokenStore.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("EventStream", () => {
  it("decodes one-byte chunks, CRLF, CR, LF, multiline data, defaults, and comments", async () => {
    const feed = source();
    const { stream, onEvent } = start(async () => feed.response);
    const event = envelope("RunStarted", 1, { payload: { title: "План 🚀" } });
    const { payload, ...header } = event;
    feed.writeBytes(
      `retry: 2000\r\n: ping 42\r\nid: 1\revent: RunStarted\ndata: ${JSON.stringify(header).slice(0, -1)},\r\n`
      + `data: "payload":${JSON.stringify(payload)}}\r\r`
      + "id: 2\nevent: RunStarted\ndata: {invalid}\n\n"
      + frame(3, "RunFinished"),
    );
    await tick();
    expect(onEvent.mock.calls).toEqual([[event], [envelope("RunFinished", 3)]]);
    expect(stream.cursor).toBe(3);
  });

  it("uses authenticated transport filters and starts at head when no after was supplied", async () => {
    const feed = source();
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(feed.response);
    const onEvent = vi.fn();
    const onCursor = vi.fn();
    const transport = new HttpTransport({ fetch, getToken: () => token, clientVersion: "2.1.0" });
    const sub = transport.events({
      workspaceId, streams: [`run:${runId}`, `project:${projectId}`],
      types: ["RunStarted", "urn:skm:execution:event:run-finished:v1"],
    }, { onEvent, onCursor });
    const [path, request] = fetch.mock.calls[0] ?? [];
    const url = new URL(String(path), "https://skm.test");
    expect(url.pathname).toBe("/api/v1/events");
    expect(url.searchParams.get("workspace_id")).toBe(workspaceId);
    expect(url.searchParams.has("after")).toBe(false);
    expect(url.searchParams.getAll("stream")).toEqual([`run:${runId}`, `project:${projectId}`]);
    expect(url.searchParams.get("types")).toBe("RunStarted,urn:skm:execution:event:run-finished:v1");
    const headers = new Headers(request?.headers);
    expect(request).toMatchObject({ method: "GET", credentials: "omit", redirect: "error" });
    expect(headers.get("Authorization")).toBe(`Bearer ${token}`);
    expect(headers.get("Accept")).toBe("text/event-stream");
    expect(headers.get("SKM-Client-Version")).toBe("2.1.0");
    expect(headers.get("X-Request-Id")).toMatch(/^web-[0-9a-f-]{36}$/u);
    expect(headers.has("Last-Event-ID")).toBe(false);
    feed.write(cursor(30) + frame(28) + frame(31));
    await tick();
    expect(onCursor.mock.calls).toEqual([[30], [31]]);
    expect(onEvent.mock.calls).toEqual([[envelope("RunStarted", 31)]]);
    sub.close();
    expect(request?.signal?.aborted).toBe(true);
    expect(feed.cancel).toHaveBeenCalledOnce();
  });

  it("advances on cursor without invalidation and resumes without replaying duplicates", async () => {
    const first = source();
    const next = source();
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const fetch = vi.fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(first.response).mockResolvedValueOnce(next.response);
    const onEvent = vi.fn((event: EventEnvelope) => invalidateEvent(queryClient, scope, event));
    const { stream } = start(fetch, { queryClient, onEvent });
    first.write(cursor(10));
    await tick();
    expect(stream.cursor).toBe(10);
    expect(onEvent).not.toHaveBeenCalled();
    expect(invalidate).not.toHaveBeenCalled();

    first.write(frame(11));
    first.end();
    await tick(1_000);
    expect(new Headers(fetch.mock.calls[1]?.[1]?.headers).get("Last-Event-ID")).toBe("11");
    next.write(cursor(9) + frame(9) + frame(11) + frame(12, "RunFinished"));
    await tick();
    expect(onEvent.mock.calls.map(([event]) => event.workspace_seq)).toEqual([11, 12]);
    expect(stream.cursor).toBe(12);
  });

  it("marks all cached data stale and notifies on snapshot-required", async () => {
    const feed = source();
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const onSnapshotRequired = vi.fn();
    const { onEvent, stream } = start(async () => feed.response, { queryClient, onSnapshotRequired });
    for (const queryKey of [scoped.run(runId), ["instance"]]) queryClient.setQueryData(queryKey, "cached");
    feed.write(cursor(40) + 'event: snapshot-required\ndata: {"reason":"cursor_expired"}\n\n');
    await tick();
    expect(invalidate.mock.calls).toEqual([[]]);
    expect(queryClient.getQueryCache().getAll().every((query) => query.state.isInvalidated)).toBe(true);
    expect(onSnapshotRequired).toHaveBeenCalledOnce();
    expect(stream.cursor).toBe(40);
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("keeps instance events and events of other workspaces out of domain dispatch", async () => {
    const feed = source();
    const { onEvent, stream } = start(async () => feed.response);
    feed.write(frame(1, "PackInstalled", { stream_kind: "pack", workspace_id: null })
      + frame(2, "HostRegistered", { stream_kind: "host", workspace_id: null })
      + frame(3, "ConfigChanged", { stream_kind: "config", workspace_id: null, payload: { scope: { level: "instance" } } })
      + frame(4, "RunStarted", { workspace_id: otherWorkspace }) + cursor(4));
    await tick();
    expect(onEvent).not.toHaveBeenCalled();
    expect(stream.cursor).toBe(4);
  });

  it("backs off on network/429/503 from 1s to 30s and resets on a 200 open", async () => {
    const closed = source();
    closed.end();
    const fetch = vi.fn<typeof globalThis.fetch>(async () => problem(503, "BACKEND_UNAVAILABLE"))
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockImplementationOnce(async () => problem(429, "TOO_MANY_STREAMS"))
      .mockImplementationOnce(async () => problem(503, "BACKEND_UNAVAILABLE"))
      .mockImplementationOnce(async () => problem(429, "TOO_MANY_STREAMS"))
      .mockImplementationOnce(async () => problem(503, "BACKEND_UNAVAILABLE"))
      .mockImplementationOnce(async () => problem(429, "TOO_MANY_STREAMS"))
      .mockImplementationOnce(async () => problem(503, "BACKEND_UNAVAILABLE"))
      .mockResolvedValueOnce(closed.response);
    const onError = vi.fn();
    start(fetch, { onError });
    await tick();
    for (const [index, delay] of [1000, 2000, 4000, 8000, 16000, 30000, 30000, 1000].entries()) {
      await tick(delay - 1);
      expect(fetch).toHaveBeenCalledTimes(index + 1);
      await tick(1);
      expect(fetch).toHaveBeenCalledTimes(index + 2);
    }
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ status: 429, code: "TOO_MANY_STREAMS" }));
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ status: 503, code: "BACKEND_UNAVAILABLE" }));
  });

  it.each([[10, 1_000], [3_000, 3_000]])("honors retry: %d with reconnect delay %d", async (retry, delay) => {
    const feed = source();
    feed.write(`retry: ${retry}\r\n\r\n`);
    feed.end();
    const fetch = vi.fn<typeof globalThis.fetch>(async () => problem(404, "NOT_FOUND"))
      .mockResolvedValueOnce(feed.response);
    start(fetch);
    await tick();
    await tick(delay - 1);
    expect(fetch).toHaveBeenCalledOnce();
    await tick(1);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it.each([[403, "FORBIDDEN"], [404, "NOT_FOUND"]] as const)("halts on %d without signing out", async (status, code) => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => problem(status, code));
    const onError = vi.fn();
    const onUnauthorized = vi.fn();
    const stream = new EventStream({ workspaceId }, { onEvent: vi.fn(), onError }, { fetch, onUnauthorized });
    streams.push(stream);
    await tick(120_000);
    expect(fetch).toHaveBeenCalledOnce();
    expect(onError).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ status, code }));
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

describe("StreamProvider", () => {
  it("hands the initial GET cursor to SSE and receives the event committed before subscribing", async () => {
    const feed = source();
    const order: string[] = [];
    const { result, events } = mount(async (input) => {
      if (String(input).startsWith("/api/v1/events?")) {
        order.push("subscribe");
        feed.write(frame(21));
        return feed.response;
      }
      order.push("GET");
      return Response.json({ state: "created" }, { headers: { "SKM-Events-Cursor": "20" } });
    });
    const { client, auth, stream } = result.current;
    const queryKey = scoped.run(runId);
    await act(async () => {
      await client.fetchQuery({
        queryKey,
        queryFn: async ({ signal }) => {
          const read = () => auth.transport.request("GET", `/api/v1/runs/${runId}`, { signal });
          const response = await stream.readWithEvents(read, signal);
          expect(response.eventsCursor).toBe(20);
          return response.data;
        },
      });
    });
    await tick(1);
    expect(order).toEqual(["GET", "subscribe"]);
    const [path, request] = events()[0] ?? [];
    expect(new URL(String(path), "https://skm.test").searchParams.get("after")).toBe("20");
    expect(new Headers(request?.headers).get("Last-Event-ID")).toBe("20");
    expect(client.getQueryState(queryKey)?.isInvalidated).toBe(true);
  });

  it("reuses an open feed at or behind the GET cursor and refetches an older snapshot", async () => {
    const feed = source();
    const snapshots = [42, 43, 41, 42];
    const { result, events } = mount(async (input) => {
      if (String(input).startsWith("/api/v1/events?")) return feed.response;
      const value = snapshots.shift();
      return Response.json({ value }, { headers: { "SKM-Events-Cursor": String(value) } });
    });
    act(() => result.current.stream.connectAtHead());
    feed.write(cursor(42));
    await tick();
    const read = () => result.current.auth.transport.request("GET", `/api/v1/runs/${runId}`);
    for (const expected of [42, 43, 42]) {
      expect((await result.current.stream.readWithEvents(read)).eventsCursor).toBe(expected);
    }
    expect(snapshots).toEqual([]);
    expect(events()).toHaveLength(1);
  });

  it("replaces an unresolved head subscription with replay from the GET cursor", async () => {
    const head = source();
    const replay = source();
    const feeds = [head, replay];
    const { result, events } = mount(async (input) => {
      if (String(input).startsWith("/api/v1/events?")) return feeds.shift()?.response ?? problem(404, "NOT_FOUND");
      return Response.json({}, { headers: { "SKM-Events-Cursor": "0" } });
    });
    const { auth, stream } = result.current;
    act(() => stream.connectAtHead());
    await tick();
    await act(async () => {
      await stream.readWithEvents(() => auth.transport.request("GET", `/api/v1/runs/${runId}`));
    });
    const [path, request] = events()[1] ?? [];
    expect(head.cancel).toHaveBeenCalledOnce();
    expect(new URL(String(path), "https://skm.test").searchParams.get("after")).toBe("0");
    expect(new Headers(request?.headers).get("Last-Event-ID")).toBe("0");
  });

  it.each([403, 404])("opens a new feed from a fresh GET after SSE stops with %d", async (status) => {
    const feed = source();
    const replay = source();
    const { result, events } = mount(async (input) => {
      if (!String(input).startsWith("/api/v1/events?")) {
        return Response.json({}, { headers: { "SKM-Events-Cursor": "15" } });
      }
      if (String(input).endsWith("after=15")) return replay.response;
      return events().length === 1 ? feed.response : problem(status, status === 403 ? "FORBIDDEN" : "NOT_FOUND");
    });
    const { auth, client, stream } = result.current;
    client.setQueryData(scoped.run(runId), "snapshot");
    act(() => stream.connectAtHead());
    feed.write(cursor(12));
    await tick();
    feed.end();
    await tick(120_000);
    expect(events()).toHaveLength(2);
    expect(new Headers(events()[1]?.[1]?.headers).get("Last-Event-ID")).toBe("12");
    await act(async () => {
      await stream.readWithEvents(() => auth.transport.request("GET", `/api/v1/runs/${runId}`));
    });
    expect(events()).toHaveLength(3);
    const [path, request] = events()[2]!;
    expect(new URL(String(path), "https://skm.test").searchParams.get("after")).toBe("15");
    expect(new Headers(request?.headers).get("Last-Event-ID")).toBe("15");
    replay.write(frame(16));
    await tick(1);
    expect(client.getQueryState(scoped.run(runId))?.isInvalidated).toBe(true);
  });

  it("signs out through AuthProvider when a revoked connection reconnects with 401", async () => {
    const feed = source();
    let revoked = false;
    const { result, events } = mount(async () => revoked ? problem(401, "UNAUTHENTICATED") : feed.response);
    const { client } = result.current;
    client.setQueryData(scoped.run(runId), "private");
    act(() => result.current.stream.connectAtHead());
    feed.write(cursor(12));
    await tick();
    revoked = true;
    feed.end();
    await tick(1_000);
    expect(events()).toHaveLength(2);
    expect(new Headers(events()[1]?.[1]?.headers).get("Last-Event-ID")).toBe("12");
    expect(result.current.auth.token).toBeNull();
    expect(tokenStore.get()).toBeNull();
    expect(result.current.pathname).toBe("/login");
    expect(client.getQueryState(scoped.run(runId))).toBeUndefined();
    await tick(120_000);
    expect(events()).toHaveLength(2);
  });

  it("aborts and purges previous scopes, isolates in-flight reads and resets the cursor", async () => {
    const first = source();
    const second = source();
    const third = source();
    const feeds = [first, second, third];
    const { result, events, unmount } = mount(async () => feeds.shift()?.response ?? problem(404, "NOT_FOUND"));
    const { client, navigate, stream } = result.current;
    const next = keys.forScope({ workspaceId, projectId: otherProject });
    const unrelated = keys.forScope({ workspaceId: otherWorkspace, projectId: otherProject });
    const oldRun = scoped.run(runId);
    const nextRun = next.run(runId);
    client.setQueryData(oldRun, "old");
    client.setQueryData(nextRun, "next");
    client.setQueryData(unrelated.run(runId), "other workspace");
    const remove = vi.spyOn(client, "removeQueries");
    let finishRead!: (response: ApiResponse<string>) => void;
    const pending = new Promise<ApiResponse<string>>((resolve) => { finishRead = resolve; });
    const late = stream.readWithEvents(() => pending);
    const rejected = expect(late).rejects.toMatchObject({ name: "AbortError" });

    act(() => stream.connectAtHead());
    first.write(cursor(99));
    await tick();
    await act(async () => { await navigate(locationFor(workspaceId, otherProject)); });
    finishRead({ data: "old", etag: null, requestId: "late", replayed: false, eventsCursor: 99 });
    await rejected;
    expect(first.cancel).toHaveBeenCalledOnce();
    expect(events()[0]?.[1]?.signal?.aborted).toBe(true);
    expect(remove).toHaveBeenCalledWith({ queryKey: keys.scope(scope) });
    expect(client.getQueryData(oldRun)).toBeUndefined();
    expect(client.getQueryData(nextRun)).toBe("next");
    expect(client.getQueryData(unrelated.run(runId))).toBe("other workspace");

    act(() => result.current.stream.connectAtHead());
    expect(new Headers(events()[1]?.[1]?.headers).has("Last-Event-ID")).toBe(false);
    await tick();
    await act(async () => { await navigate(locationFor(otherWorkspace, otherProject)); });
    expect(second.cancel).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledWith({ queryKey: keys.workspace(workspaceId) });
    expect(client.getQueryData(nextRun)).toBeUndefined();
    expect(client.getQueryData(unrelated.run(runId))).toBe("other workspace");
    act(() => result.current.stream.connectAtHead());
    expect(new URL(String(events()[2]?.[0]), "https://skm.test").searchParams.get("workspace_id")).toBe(otherWorkspace);
    await tick();
    unmount();
    expect(third.cancel).toHaveBeenCalledOnce();
  });

});

describe("authenticated shell", () => {
  it.each([[12, 15], [15, 12]])("subscribes at the earliest cursor from project %i and workspace %i", async (projectCursor, workspaceCursor) => {
    vi.useRealTimers();
    const feed = source();
    const projectPath = `/api/v1/projects/${projectId}`;
    const workspacePath = `/api/v1/workspaces/${workspaceId}`;
    const fetch = stubFetch(async (input) => {
      const path = String(input);
      if (path === "/api/v1/me") return Response.json(testIdentity);
      if (path === projectPath || path === workspacePath) {
        const cursor = path === projectPath ? projectCursor : workspaceCursor;
        return Response.json({ workspace_id: workspaceId }, { headers: { "SKM-Events-Cursor": String(cursor) } });
      }
      if (path.startsWith("/api/v1/events?")) return feed.response;
      throw new Error(`Unexpected GET ${path}`);
    });

    history.replaceState(null, "", `/p/${projectId}`);
    render(createElement(App, { initialToken: token }));

    const scopeRequests = () => fetch.mock.calls.map(([path]) => String(path))
      .filter((path) => path === projectPath || path === workspacePath || path.startsWith("/api/v1/events?"));
    await waitFor(() => expect(scopeRequests()).toHaveLength(3));
    expect(scopeRequests()).toEqual([projectPath, workspacePath, `/api/v1/events?workspace_id=${workspaceId}&after=12`]);
  });

  it.each([
    [`/?workspace_id=${workspaceId}`, undefined],
    [`/p/${projectId}`, 2],
    ["/w/example", 2],
  ] as const)("uses the workspace GET cursor and clears the stale badge on reconnect at %s", async (entry, seconds) => {
    vi.useRealTimers();
    const first = source();
    const recovered = source();
    let live: Response | undefined = first.response;
    const workspacePath = `/api/v1/workspaces/${workspaceId}`;
    const fetch = stubFetch(async (input) => {
      const path = String(input);
      if (path === "/api/v1/me") return Response.json({ ...testIdentity, effective_permissions: ["config.read"] });
      if (path === "/api/v1/config/effective?scope=instance&keys=ui.stale_after_seconds") {
        return Response.json({ keys: seconds === undefined ? [] : [{ key: "ui.stale_after_seconds", value: seconds }] });
      }
      if (path === "/api/v1/workspaces") return Response.json({ items: [], next: "next-page" });
      if (path === "/api/v1/workspaces?after=next-page") {
        return Response.json({ items: [{ workspace_id: workspaceId, slug: "example" }], next: null });
      }
      if (path === `/api/v1/projects/${projectId}`) return Response.json({ workspace_id: workspaceId });
      if (path === workspacePath) return Response.json({ workspace_id: workspaceId }, { headers: { "SKM-Events-Cursor": "12" } });
      if (path.startsWith("/api/v1/events?")) return live ?? problem(503, "BACKEND_UNAVAILABLE");
      throw new Error(`Unexpected GET ${path}`);
    });
    history.replaceState(null, "", entry);
    render(createElement(App, { initialToken: token }));
    const requests = () => fetch.mock.calls.map(([path]) => String(path));
    const streamPath = `/api/v1/events?workspace_id=${workspaceId}&after=12`;
    await waitFor(() => expect(requests()).toContain(streamPath));
    expect(requests().indexOf(workspacePath)).toBeLessThan(requests().indexOf(streamPath));
    expect(screen.getByText("API доступен")).toBeTruthy();
    vi.useFakeTimers();
    live = undefined;
    first.end();
    await tick();
    const threshold = (seconds ?? 30) * 1_000;
    await tick(threshold);
    expect(screen.queryByText("Данные устарели")).toBeNull();
    await tick(1);
    expect(screen.getByText("Данные устарели").getAttribute("data-tone")).toBe("warning");
    live = recovered.response;
    await tick(30_000);
    expect(screen.queryByText("Данные устарели")).toBeNull();
    expect(screen.getByText("API доступен")).toBeTruthy();
  });
});

describe("query invalidation", () => {
  const id = (n: number) => `0192f5c5-0a10-7b22-8f00-${String(n).padStart(12, "0")}` as Uuid;
  const [plan, draft, task, attempt] = [id(1), id(2), id(3), id(4)];
  const [file, output, intent, review] = [id(5), id(6), id(7), id(8)];
  const [stage, worker, host, assignment] = [id(9), id(10), id(11), id(12)];
  const by = testIdentity.principal.principal_id;
  const digest = `sha256:${"a".repeat(64)}`;
  const cause = { trigger_kind: "manual_start", advance_rule: null, reason_codes: [], refs: [] } as const;
  const config = `project:${projectId}`;
  const configKey = "execution.review.grouping";
  const secondConfigKey = "execution.review.final_correction";
  const configPayload = { scope: { level: "project", scope_id: projectId }, generation: 2 } as const;
  const runRef = { workspace_id: workspaceId, project_id: projectId, run_id: runId };
  const taskRef = { ...runRef, task_id: task };
  const attemptRef = { ...taskRef, attempt_id: attempt };
  const runKeys = [scoped.run(runId), scoped.runs(projectId)];
  const taskKeys = [scoped.runTasks(runId), scoped.task(task), scoped.run(runId)];
  const attemptKeys = [scoped.attempt(attempt), scoped.task(task)];
  const intentKeys = [scoped.inbox(), scoped.run(runId)];
  const plans = [scoped.plans(projectId), scoped.plan(plan)];
  const draftKeys = [scoped.draft(draft), [...scoped.draft(draft), "validation", 1], scoped.draftPreview(draft, plan)];
  const files = [scoped.files(projectId), scoped.file(file)];
  const configKeys = [scoped.configExplain(config), scoped.configHistory(config, configKey)];

  function wire(owner: string, stream_kind: EventEnvelope["stream_kind"], stream_id: Uuid) {
    return (name: string, payload: EventEnvelope["payload"], affected: QueryKey[]) =>
      ({ name, event: envelope(`urn:skm:${owner}:event:${name}:v1`, 1, { stream_kind, stream_id, payload }), affected });
  }
  const run = wire("execution", "run", runId);
  const planning = wire("planning", "plan", plan);
  const artifacts = wire("artifacts", "file", file);
  const policy = wire("policy", "intent", intent);
  const settings = wire("settings", "config", projectId);
  const leaseExpired = run("lease-expired", {
    ...runRef, assignment_id: assignment, attempt_id: attempt, worker_id: worker, fencing_token: 1,
  } satisfies Execution.LeaseExpired, taskKeys);
  const reviewCompleted = run("review-completed", {
    ...taskRef, review_id: review, output_id: output, round_no: 1, profile_key: "reviewer", verdict: "green",
    finding_counts: {}, new_finding_keys: [], evidence_refs: [], cause: { ...cause },
  } satisfies Execution.ReviewCompleted, attemptKeys);
  const intentProposed = policy("intent-proposed", {
    intent_id: intent, scope_id: runId, kind: "git_push", risk: "high",
    args_digest: digest, state: "proposed", subject_ref: `attempt:${attempt}`,
  } satisfies Policy.IntentProposed, intentKeys);
  const intentResolved = policy("intent-resolved", { intent_id: intent, outcome: "succeeded" } satisfies Policy.IntentResolved, intentKeys);
  const cases = [
    planning("plan-created", { plan_id: plan, workspace_id: workspaceId, project_id: projectId, alias: "PLAN1", title: "Plan", purpose: "standard" } satisfies Planning.PlanCreated, plans),
    planning("plan-archived", { plan_id: plan, project_id: projectId, alias: "PLAN1", abandoned_draft_ids: [] } satisfies Planning.PlanArchived, plans),
    planning("draft-saved", { plan_id: plan, draft_id: draft, edit_version: 1, document_digest: digest, counts: { error: 0, warning: 0, info: 0 } } satisfies Planning.DraftSaved, draftKeys),
    planning("draft-abandoned", { plan_id: plan, draft_id: draft, edit_version: 1, reason: "user" } satisfies Planning.DraftAbandoned, draftKeys),
    planning("plan-revision-published", { plan_id: plan, revision_id: id(13), revision_no: 1, parent_revision_id: null, content_digest: digest, title: "Plan", origin: "draft", draft_id: draft } satisfies Planning.PlanRevisionPublished, [...plans, scoped.revisions(plan), scoped.draftPreview(draft, plan)]),
    run("run-created", { ...runRef, plan_id: plan, revision_id: id(13), revision_no: 1, kind: "plan", requested_by: by, bundle_digest: digest, cause: { ...cause } } satisfies Execution.RunCreated, runKeys),
    run("run-started", { ...runRef, task_count: 1, ready_count: 1, bundle_digest: digest, review_grouping: "none" } satisfies Execution.RunStarted, runKeys),
    run("run-paused", { ...runRef, reason: "Paused", by, pause_source: "manual" } satisfies Execution.RunPaused, runKeys),
    run("run-resumed", { ...runRef, by } satisfies Execution.RunResumed, runKeys),
    run("run-waiting", { ...runRef, waiting: [] } satisfies Execution.RunWaiting, runKeys),
    run("run-finished", { ...runRef, outcome: "succeeded", counts_by_status: { accepted: 1 } } satisfies Execution.RunFinished, runKeys),
    run("run-cancelled", { ...runRef, reason: "Cancelled", by } satisfies Execution.RunCancelled, runKeys),
    run("task-created", { ...taskRef, kind: "unit", revision_id: id(13), entity_id: id(14), origin: null, cause, initial_state: "ready", position: 1, parent_task_id: null } satisfies Execution.TaskCreated, taskKeys),
    run("task-ready", { ...taskRef, display_key: "P1.1/U1", reason: "dependencies_satisfied", cause } satisfies Execution.TaskReady, taskKeys),
    run("task-assigned", { ...attemptRef, assignment_id: assignment, attempt_no: 1, attempt_state: "assigned", cause } satisfies Execution.TaskAssigned, taskKeys),
    run("task-wait-changed", { ...attemptRef, previous_code: null, code: "WAITING_MANUAL_CHECK", started_at: testIdentity.principal.created_at, finished_at: null, cause } satisfies Execution.TaskWaitChanged, taskKeys),
    run("task-rework-required", { ...attemptRef, reason: "review_changes", round: 1, input_output_id: output, check_execution_ids: [], cause: { ...cause } } satisfies Execution.TaskReworkRequired, taskKeys),
    run("task-accepted", { ...taskRef, clearance: "no_review", carried_forward: false } satisfies Execution.TaskAccepted, taskKeys),
    run("task-failed", { ...taskRef, code: "CHECKS_FAILED" } satisfies Execution.TaskFailed, taskKeys),
    run("task-skipped", { ...taskRef, reason: "Skipped", by } satisfies Execution.TaskSkipped, taskKeys),
    run("assignment-leased", { ...attemptRef, assignment_id: assignment, worker_id: worker, host_id: host, fencing_token: 1 } satisfies Execution.AssignmentLeased, taskKeys),
    leaseExpired,
    run("attempt-started", { ...attemptRef, attempt_no: 1, worker_id: worker, host_id: host } satisfies Execution.AttemptStarted, attemptKeys),
    run("stage-started", { ...attemptRef, stage_record_id: stage, stage_id: "execute", stage_type: "execute", round_no: 1, mode: "fresh", skipped_stage_ids: [], input_digest: digest, feedback_refs: [], step_refs: [], effective_config_digest: digest, reconfiguration_ids: [], cause: { ...cause } } satisfies Execution.StageStarted, attemptKeys),
    run("stage-completed", { ...attemptRef, stage_record_id: stage, stage_id: "execute", stage_type: "execute", state: "completed", diagnostics: [], step_ids: [], step_states: {}, output_ids: [output], check_execution_ids: [], review_ids: [], decision_ids: [], effect_ids: [], observation_refs: [], timing: {}, coverage: {}, cause: { ...cause } } satisfies Execution.StageCompleted, attemptKeys),
    run("output-sealed", { ...attemptRef, output_id: output, seq: 1, source: "executor", manifest_digest: digest, tree_digest: digest, files_changed: 1, outside_write_scope_count: 0, excluded_count: 0, cause: { ...cause } } satisfies Execution.OutputSealed, attemptKeys),
    run("check-completed", { ...attemptRef, stage_record_id: stage, output_id: output, round_no: 1, results: [], cause: { ...cause } } satisfies Execution.CheckCompleted, attemptKeys),
    reviewCompleted,
    run("decision-requested", { ...runRef, request_id: id(15), kind: "approval", audience: "operator", blocking_code: "WAITING_APPROVAL" } satisfies Execution.DecisionRequested, intentKeys),
    run("decision-answered", { ...runRef, request_id: id(15), kind: "approval", answered_by_kind: "human", record_as_plan_decision: false } satisfies Execution.DecisionAnswered, intentKeys),
    run("manual-verdict-recorded", { ...runRef, check_execution_id: id(16), check_key: "V1", verdict: "pass", by } satisfies Execution.ManualVerdictRecorded, intentKeys),
    run("deviation-accepted", { ...taskRef, deviation_id: id(17), scope: "task", by } satisfies Execution.DeviationAccepted, intentKeys),
    intentProposed, intentResolved,
    run("budget-exhausted", { ...runRef, dimension: "usd", scope: "run", limit: 5, spent: 5 } satisfies Execution.BudgetExhausted, [scoped.runBudget(runId)]),
    settings("config-changed", {
      ...configPayload, keys: [configKey, secondConfigKey], changes: { [configKey]: "updated", [secondConfigKey]: "created" },
    } satisfies Settings.ConfigChanged, [...configKeys, scoped.configHistory(config, secondConfigKey)]),
    settings("config-locked", { ...configPayload, key: configKey } satisfies Settings.ConfigLocked, configKeys),
    settings("config-unlocked", { ...configPayload, key: configKey } satisfies Settings.ConfigUnlocked, configKeys),
    artifacts("file-added", { file_id: file, workspace_id: workspaceId, project_id: projectId, title: "Report", origin: "upload", classification: "internal" } satisfies Artifacts.FileAdded, files),
    artifacts("file-version-added", { file_id: file, file_version_id: id(18), version_no: 1, size_bytes: 12, digest, safety_verdict: "ok" } satisfies Artifacts.FileVersionAdded, files),
    artifacts("file-trashed", { file_id: file, reason: "Removed" } satisfies Artifacts.FileTrashed, files),
    wire("workspace", "workspace", workspaceId)("worker-state-changed", { worker_id: worker, from_state: "online", to_state: "offline" } satisfies Workspace.WorkerStateChanged, [scoped.workers()]),
    wire("execution", "project", projectId)("autopilot-state-changed", { workspace_id: workspaceId, project_id: projectId, from: "idle", to: "running", emergency: false, by, session_reset: false } satisfies Execution.AutopilotStateChanged, [scoped.autopilot(projectId)]),
  ];

  const other = keys.forScope({ workspaceId, projectId: otherProject });
  const remote = keys.forScope({ workspaceId: otherWorkspace, projectId });
  const unrelated = [scoped.task(id(19)), scoped.attempt(id(20)), scoped.run(id(21))];

  function seed(affected: QueryKey[], untouched: QueryKey[]) {
    const client = new QueryClient();
    for (const key of [...affected, ...untouched]) client.setQueryData(key, true);
    return client;
  }

  function check(client: QueryClient, affected: QueryKey[], untouched: QueryKey[]) {
    for (const key of affected) expect(client.getQueryState(key)?.isInvalidated, JSON.stringify(key)).toBe(true);
    for (const key of untouched) expect(client.getQueryState(key)?.isInvalidated, JSON.stringify(key)).toBe(false);
  }

  it.each(cases)("$name invalidates keys from its wire payload", ({ name, event, affected }) => {
    const toast = vi.fn();
    const untouched = [...unrelated, scoped.runBudget("other-run"), scoped.configHistory(config, "different"),
      scoped.draftPreview("another-draft", "another-plan"), other.run(runId), other.task(task), remote.attempt(attempt)];
    const client = seed(affected, untouched);
    client.setQueryData(scoped.task(task), { attempts: [{ attempt_id: attempt, outputs: [{ output_id: output }] }] });
    if (name === "intent-resolved") {
      client.setQueryData(scoped.inbox(), { items: [{ run_id: runId, payload: { intent_id: intent } }] });
    }
    invalidateEvent(client, scope, event, toast);
    check(client, affected, untouched);
    if (name === "budget-exhausted") expect(toast).toHaveBeenCalledExactlyOnceWith({ message: "Бюджет запуска исчерпан" });
    else expect(toast).not.toHaveBeenCalled();
  });

  it.each([leaseExpired, reviewCompleted, intentProposed, intentResolved])("$name falls back only within its detail namespace", ({ name, event, affected }) => {
    const index = name === "lease-expired" ? 0 : name === "review-completed" ? 1 : 2;
    const stale = [...affected, unrelated[index]!];
    const untouched = [...unrelated.filter((_, i) => i !== index), scoped.runBudget(runId),
      other.task(task), other.attempt(attempt), other.run(runId), remote.task(task), remote.attempt(attempt), remote.run(runId)];
    const wireEvent = name === "intent-proposed" ? { ...event, payload: { ...event.payload, scope_id: projectId } } : event;
    const client = seed(stale, untouched);
    invalidateEvent(client, scope, wireEvent);
    check(client, stale, untouched);
  });

  it("ignores another project's run event", () => {
    const { event } = run("run-resumed", { ...runRef, project_id: otherProject, by }, runKeys);
    const client = seed([], runKeys);
    invalidateEvent(client, scope, event);
    check(client, [], runKeys);
  });
});
