import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./ApiError";
import { HttpTransport } from "./HttpTransport";

class FakeSocket {
  static all: FakeSocket[] = [];
  readyState = 0;
  sent: Array<Record<string, unknown>> = [];
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.all.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.readyState = 3;
  }
  open() {
    this.readyState = 1;
    this.onopen?.({});
  }
  frame(frame: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify({ $schema: "urn:swissknifeman:gui:stream:v1", ...frame }) });
  }
  drop() {
    this.readyState = 3;
    this.onclose?.({});
  }
}

function transport() {
  FakeSocket.all = [];
  const timers: Array<() => void> = [];
  const http = new HttpTransport({
    WebSocket: FakeSocket,
    location: { protocol: "http:", host: "127.0.0.1:8765" },
    setTimeout: (callback) => timers.push(callback),
  });
  return { http, timers };
}

const log = (seq: number, chunk: number, sub = "s1") => ({
  kind: "log", seq, sub, run_id: `run-${"a".repeat(32)}`, stream: "stdout", chunk, text: `line ${chunk}\n`, truncated: false,
});

describe("HttpTransport requests", () => {
  it("sends same-origin JSON and turns api-error/v1 into ApiError", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ error: { code: "INPUT_INVALID", class: "invalid",
      message: "bad", retryable: false, correlation_id: "c0ffee00", issues: [{ pointer: "/input/x", code: "type", message: "m" }] } }),
      { status: 422 }));
    const http = new HttpTransport({ fetch, WebSocket: FakeSocket, location: { protocol: "http:", host: "h" } });
    const error = (await http.request("POST", "/v1/commands/x.y/runs", { a: 1 }).catch((caught: unknown) => caught)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("INPUT_INVALID");
    expect(error.issues[0]?.pointer).toBe("/input/x");
    const [path, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/v1/commands/x.y/runs");
    expect(init.credentials).toBe("same-origin");
    expect(init.body).toBe('{"a":1}');
  });

  it("refuses paths outside /v1", async () => {
    const http = new HttpTransport({ fetch: vi.fn(), WebSocket: FakeSocket, location: { protocol: "http:", host: "h" } });
    await expect(http.request("GET", "https://evil.example/x")).rejects.toThrow(/not an API path/);
    await expect(http.request("GET", "/v1/../x")).rejects.toThrow(/not an API path/);
  });
});

describe("HttpTransport stream", () => {
  it("subscribes, drops duplicates and resumes after a reconnect from the last seq and epoch", () => {
    const { http, timers } = transport();
    http.setEpoch("epoch-0001");
    const frames: number[] = [];
    http.subscribe({ runs: [`run-${"a".repeat(32)}`] }, { onFrame: (frame) => frames.push(frame.seq) });
    const first = FakeSocket.all[0]!;
    expect(first.url).toBe("ws://127.0.0.1:8765/v1/events");
    first.open();
    expect(first.sent[0]).toMatchObject({ kind: "subscribe", id: "s1", cursor: null, epoch: null });
    first.frame(log(5, 0));
    first.frame(log(6, 1));
    first.frame(log(6, 1));
    first.frame({ kind: "heartbeat", seq: 7, at: "2026-10-16T00:00:00Z" });
    first.drop();
    expect(timers).toHaveLength(1);
    timers[0]!();
    const second = FakeSocket.all[1]!;
    second.open();
    expect(second.sent[0]).toMatchObject({ kind: "subscribe", id: "s1", cursor: 6, epoch: "epoch-0001" });
    second.frame(log(6, 1));
    second.frame(log(8, 2));
    expect(frames).toEqual([5, 6, 8]);
  });

  it("snapshot_required resets the cursor and tells the handler", () => {
    const { http } = transport();
    http.setEpoch("epoch-0001");
    const reasons: string[] = [];
    const seen: number[] = [];
    http.subscribe({}, { onFrame: (frame) => seen.push(frame.seq), onSnapshotRequired: (reason) => reasons.push(reason) });
    const socket = FakeSocket.all[0]!;
    socket.open();
    socket.frame(log(10, 0));
    socket.frame({ kind: "snapshot_required", sub: "s1", reason: "overflow" });
    socket.frame(log(3, 0));
    expect(reasons).toEqual(["overflow"]);
    expect(seen).toEqual([10, 3]);
  });

  it("a new epoch forgets the cursors; closing the last subscription closes the socket", () => {
    const { http } = transport();
    http.setEpoch("epoch-0001");
    const subscription = http.subscribe({}, { onFrame: () => undefined });
    const socket = FakeSocket.all[0]!;
    socket.open();
    socket.frame(log(4, 0));
    http.setEpoch("epoch-0002");
    subscription.close();
    expect(socket.sent.at(-1)).toMatchObject({ kind: "unsubscribe", id: "s1" });
    expect(socket.readyState).toBe(3);
  });
});
