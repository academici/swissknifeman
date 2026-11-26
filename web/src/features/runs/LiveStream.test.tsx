// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import "../../../tests/setup";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import type { IsoDateTime, Uuid } from "../../api/generated/kernel";
import { keys } from "../../api/keys";
import { AuthProvider } from "../../app/providers/AuthProvider";
import { ScopeProvider } from "../../app/providers/ScopeProvider";
import { StreamProvider } from "../../app/providers/StreamProvider";
import { ToastProvider } from "../../app/providers/ToastProvider";
import { LiveStream } from "./LiveStream";

const attemptId = "attempt-a" as Uuid;
const scope = { workspaceId: "ws-a", projectId: "project-a" };
const key = keys.forScope(scope).attempt(attemptId);
const unsafe = "<img src=x>\u202etest";

function stream(text: string) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({ start(controller) {
    for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.subarray(i, i + 7));
    controller.close();
  } }), { headers: { "Content-Type": "text/event-stream" } });
}

function frame(id: number, type: string, data: object) {
  return `id: ${id}\r\nevent: ${type}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
}

function open(live: (index: number) => Response, options: { enabled?: boolean; finished?: boolean } = {}) {
  const headers: Headers[] = [];
  let contentReads = 0;
  const fetch = stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    switch (url.pathname) {
      case "/api/v1/me": return Response.json(testIdentity);
      case "/api/v1/config/effective": return Response.json({ keys: [{ key: "ui.runs.live_stream", value: options.enabled ?? true }] },
        { headers: { "SKM-Events-Cursor": "9876" } });
      case "/api/v1/events": return new Response(new ReadableStream());
      case "/api/v1/attempts/attempt-a/live":
        headers.push(new Headers(init?.headers));
        return live(headers.length - 1);
      case "/api/v1/steps/step-a":
      case "/api/v1/steps/step-b": return Response.json({
        payload_visibility: url.pathname.endsWith("step-a") ? "available" : "restricted", transcript_file_version_id: "version-a",
      });
      case "/api/v1/file-versions/version-a/content":
        contentReads++;
        return new Response(unsafe);
      default: throw Error(url.pathname);
    }
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(key, {});
  const attempt = { attempt_id: attemptId, finished_at: options.finished ? "2026-01-02T00:00:00Z" as IsoDateTime : null,
    steps: [{ step_id: "step-a" }, { step_id: "step-b" }] };
  render(<MemoryRouter initialEntries={["/attempts/attempt-a?project_id=project-a&workspace_id=ws-a"]}>
    <QueryClientProvider client={client}><AuthProvider initialToken="live-token"><ScopeProvider>
      <ToastProvider><StreamProvider><Routes>
        <Route path="/attempts/:id" element={<LiveStream attempt={attempt} {...scope} />} />
        <Route path="/login" element={<h1>Вход</h1>} />
      </Routes></StreamProvider></ToastProvider>
    </ScopeProvider></AuthProvider></QueryClientProvider>
  </MemoryRouter>);
  return { client, fetch, headers, contentReads: () => contentReads };
}

describe("LiveStream", () => {
  it("resumes from complete live frames, honors reset and eviction gaps, then stops at end", async () => {
    const delta = { type: "text_delta", channel: "reasoning", text: unsafe, seq: 55 };
    const responses = [
      frame(4, delta.type, delta) + ": ping 123\n\n" + "id: 5\nevent: text_delta\ndata: {",
      frame(0, "gap", { reason: "buffer_missing", after: 4, oldest: null }),
      frame(8, "gap", { reason: "buffer_evicted", after: 0, oldest: 9 }) +
        frame(9, "tool_requested", { type: "tool_requested", tool: "test", call_id: "c", args_preview: unsafe }) +
        frame(10, "session_failed", { type: "session_failed", failure: { code: "FAIL", safe_message: unsafe } }) +
        "event: end\ndata: {}\n\n",
    ];
    const app = open(index => stream(responses[index] ?? ""));
    const list = await screen.findByRole("list", { name: "События попытки" });
    expect(within(list).getByText(/reasoning · <img src=x>\\u202etest/u)).toBeTruthy();
    expect((await screen.findByRole("alert", {}, { timeout: 2500 })).textContent).toContain("buffer_missing · после 4");
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Поток завершён"), { timeout: 2500 });
    expect(screen.getByRole("alert").textContent).toContain("buffer_evicted · после 0");
    expect(list.querySelector("img")).toBeNull();
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(app.headers.map(header => header.get("Last-Event-ID"))).toEqual([null, "4", "0"]);
    expect(app.headers.every(header => header.get("Authorization") === "Bearer live-token")).toBe(true);
    expect(new Set(app.headers.map(header => header.get("X-Request-Id"))).size).toBe(3);
    expect(app.client.getQueryState(key)?.isInvalidated).toBe(true);

    const openTranscript = screen.getByRole("button", { name: "Открыть транскрипт шага step-a" });
    const user = userEvent.setup();
    await user.hover(openTranscript);
    expect(app.contentReads()).toBe(0);
    expect(screen.queryByRole("button", { name: /транскрипт шага step-b/u })).toBeNull();
    await user.click(openTranscript);
    expect(await screen.findByText("<img src=x>\\u202etest", { selector: "code" })).toBeTruthy();
    expect(app.contentReads()).toBe(1);
    await new Promise(resolve => setTimeout(resolve, 1100));
    expect(app.headers).toHaveLength(3);
  });

  it("displays runtime, tool, usage and terminal session events in delivery order", async () => {
    const events = [
      { type: "session_started", model: "model-A", runtime_version: "v2", session_ref: "s1" },
      { type: "tool_completed", call_id: "c1", status: "ok", duration_ms: 12 },
      { type: "usage_reported", usage: { input_tokens: 321 }, cumulative: true },
      { type: "checkpoint_available", session_ref: "s2" },
      { type: "cancel_ignored", signal: "SIGTERM" },
      { type: "session_completed", stop_reason: "end_turn" },
    ];
    const app = open(() => stream(events.map((event, i) => frame(i + 1, event.type, event)).join("") +
      "event: end\ndata: {}\n\n"));
    const list = await screen.findByRole("list", { name: "События попытки" });
    expect(within(list).getAllByRole("listitem").map(item => item.textContent)).toEqual([
      "session_started model-A · v2 · s1", "tool_completed c1 · ok · 12 мс", 'usage_reported {"input_tokens":321}',
      "checkpoint_available s2", "cancel_ignored SIGTERM", "session_completed end_turn",
    ]);
    expect(app.contentReads()).toBe(0);
  });

  it("stops on the stream limit and retains the request ID", async () => {
    const app = open(() => Response.json({ code: "TOO_MANY_STREAMS", category: "limit", request_id: "stream-limit" },
      { status: 429, headers: { "Content-Type": "application/problem+json" } }));
    const error = await screen.findByRole("alert");
    expect(error.textContent).toContain("TOO_MANY_STREAMS");
    expect(error.textContent).toContain("stream-limit");
    expect(within(error).queryByRole("button")).toBeNull();
    await new Promise(resolve => setTimeout(resolve, 1100));
    expect(app.headers).toHaveLength(1);
  });

  it("signs out when the live token is revoked", async () => {
    const app = open(() => new Response(null, { status: 401 }));
    expect(await screen.findByRole("heading", { name: "Вход" })).toBeTruthy();
    expect(app.headers).toHaveLength(1);
    expect(app.client.getQueryState(key)).toBeUndefined();
  });

  it("hides unauthorized attempts and avoids opening their transcripts", async () => {
    const app = open(() => new Response(null, { status: 404 }));
    await waitFor(() => expect(app.headers).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Прямой эфир попытки" })).toBeNull());
    expect(app.contentReads()).toBe(0);
  });

  it.each([{ enabled: false }, { finished: true }])("subscribes only to active enabled attempts (%j)", async options => {
    const app = open(() => stream(""), options);
    if (options.finished) await screen.findByRole("heading", { name: "Сохранённые транскрипты" });
    else await waitFor(() => expect(app.client.getQueriesData({ queryKey: [...keys.scope(scope), "config", "project:project-a"] })
      .some(([, value]) => value != null)).toBe(true));
    expect(app.headers).toHaveLength(0);
    expect(app.contentReads()).toBe(0);
  });
});
