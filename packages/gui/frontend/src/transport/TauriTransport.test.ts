import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./ApiError";
import { HttpTransport } from "./HttpTransport";
import { TauriTransport, type TauriChannel, type TauriGlobal } from "./TauriTransport";
import { selectTransport } from "./select";

class FakeChannel implements TauriChannel {
  static all: FakeChannel[] = [];
  onmessage: ((message: unknown) => void) | null = null;
  constructor() {
    FakeChannel.all.push(this);
  }
  deliver(message: unknown) {
    this.onmessage?.(message);
  }
}

const log = (seq: number) => ({ kind: "log", seq, sub: "s1", run_id: `run-${"a".repeat(32)}`, stream: "stdout", chunk: seq, text: "x", truncated: false });

function setup(answers: Record<string, unknown> = {}) {
  FakeChannel.all = [];
  const invoke = vi.fn(async (command: string) => (command in answers ? answers[command] : command === "api_subscribe" ? 7 : null));
  const tauri = { core: { invoke, Channel: FakeChannel as unknown as TauriGlobal["core"]["Channel"] } } as TauriGlobal;
  const timers: Array<() => void> = [];
  const transport = new TauriTransport({ tauri, setTimeout: (callback) => timers.push(callback), clearTimeout: () => undefined });
  return { transport, invoke, timers };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

afterEach(() => {
  delete (globalThis as { __TAURI__?: unknown }).__TAURI__;
});

describe("TauriTransport request", () => {
  it("returns the body of a 2xx answer and sends a null body when there is none", async () => {
    const { transport, invoke } = setup({ api_request: { status: 200, body: { ok: 1 } } });
    await expect(transport.request("GET", "/v1/bootstrap")).resolves.toEqual({ ok: 1 });
    expect(invoke).toHaveBeenCalledWith("api_request", { method: "GET", path: "/v1/bootstrap", body: null });
  });

  it("turns status >= 400 into ApiError from the envelope", async () => {
    const { transport } = setup({
      api_request: { status: 422, body: { error: { code: "INPUT_INVALID", class: "invalid", message: "bad", retryable: false } } },
    });
    const error = (await transport.request("POST", "/v1/x", { a: 1 }).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("INPUT_INVALID");
    expect(error.status).toBe(422);
  });

  it("answers TRANSPORT_MALFORMED for an unexpected shape", async () => {
    for (const answer of ["oops", null, { body: 1 }, { status: 302, body: null }]) {
      const { transport } = setup({ api_request: answer });
      const error = (await transport.request("GET", "/v1/x").catch((e: unknown) => e)) as ApiError;
      expect(error).toBeInstanceOf(ApiError);
      expect(error.code).toBe("TRANSPORT_MALFORMED");
    }
  });

  it("refuses paths outside /v1", async () => {
    const { transport, invoke } = setup();
    await expect(transport.request("GET", "http://evil.example/x")).rejects.toThrow(/not an API path/);
    expect(invoke).not.toHaveBeenCalled();
  });
});

describe("TauriTransport stream", () => {
  it("subscribes through a Channel and delivers batched frames once", async () => {
    const { transport, invoke } = setup();
    const seen: number[] = [];
    transport.setEpoch("e1");
    transport.subscribe({ runs: ["r"] }, { onFrame: (frame) => seen.push(frame.seq) });
    await flush();
    expect(invoke).toHaveBeenCalledWith("api_subscribe", { filter: { runs: ["r"] }, channel: FakeChannel.all[0] });
    FakeChannel.all[0]!.deliver([log(1), log(2), log(2)]);
    FakeChannel.all[0]!.deliver([{ kind: "heartbeat", seq: 3, at: "t" }, log(3)]);
    expect(seen).toEqual([1, 2, 3]);
  });

  it("close() clears onmessage and calls api_unsubscribe with the id", async () => {
    const { transport, invoke } = setup();
    const seen: number[] = [];
    const subscription = transport.subscribe({}, { onFrame: (frame) => seen.push(frame.seq) });
    await flush();
    const channel = FakeChannel.all[0]!;
    subscription.close();
    expect(channel.onmessage).toBeNull();
    expect(invoke).toHaveBeenCalledWith("api_unsubscribe", { id: 7 });
    channel.deliver([log(1)]);
    expect(seen).toEqual([]);
    subscription.close();
    expect(invoke.mock.calls.filter(([command]) => command === "api_unsubscribe")).toHaveLength(1);
  });

  it("a dropped report asks for a snapshot", async () => {
    const { transport } = setup();
    const reasons: string[] = [];
    const seen: number[] = [];
    transport.subscribe({}, { onFrame: (f) => seen.push(f.seq), onSnapshotRequired: (r) => reasons.push(r) });
    await flush();
    FakeChannel.all[0]!.deliver([log(5)]);
    FakeChannel.all[0]!.deliver([{ dropped: 3 }, log(2)]);
    expect(reasons).toEqual(["overflow"]);
    expect(seen).toEqual([5, 2]);
  });

  it("resubscribes with backoff after the stream closed and reloads the data", async () => {
    const { transport, invoke, timers } = setup();
    const reasons: string[] = [];
    const seen: number[] = [];
    transport.subscribe({}, { onFrame: (f) => seen.push(f.seq), onSnapshotRequired: (r) => reasons.push(r) });
    await flush();
    FakeChannel.all[0]!.deliver([log(5)]);
    FakeChannel.all[0]!.deliver([{ closed: true }]);
    expect(timers).toHaveLength(1);
    timers[0]!();
    await flush();
    expect(reasons).toEqual(["cursor_expired"]);
    expect(invoke.mock.calls.filter(([command]) => command === "api_subscribe")).toHaveLength(2);
    FakeChannel.all[1]!.deliver([log(1)]);
    expect(seen).toEqual([5, 1]);
  });

  it("asks for the snapshot only after the replacement subscription is established", async () => {
    const { transport, invoke, timers } = setup();
    const order: string[] = [];
    transport.subscribe({}, { onFrame: () => undefined, onSnapshotRequired: () => order.push("snapshot") });
    await flush();
    FakeChannel.all[0]!.deliver([log(5)]);
    FakeChannel.all[0]!.deliver([{ closed: true }]);
    invoke.mockImplementation(async (command: string) => {
      order.push(command);
      return command === "api_subscribe" ? 8 : null;
    });
    timers[0]!();
    expect(order).toEqual(["api_subscribe"]);
    await flush();
    expect(order).toEqual(["api_subscribe", "snapshot"]);
  });

  it("retries a failed subscribe without asking for a snapshot", async () => {
    const { transport, invoke, timers } = setup();
    invoke.mockRejectedValueOnce({ code: "SIDECAR_UNAVAILABLE" });
    const reasons: string[] = [];
    transport.subscribe({}, { onFrame: () => undefined, onSnapshotRequired: (r) => reasons.push(r) });
    await flush();
    expect(timers).toHaveLength(1);
    timers[0]!();
    await flush();
    expect(reasons).toEqual([]);
    expect(FakeChannel.all).toHaveLength(2);
  });

  it("a new epoch forgets the cursor, so the same seq is delivered again", async () => {
    const { transport } = setup();
    const seen: number[] = [];
    transport.setEpoch("e1");
    transport.subscribe({}, { onFrame: (f) => seen.push(f.seq) });
    await flush();
    FakeChannel.all[0]!.deliver([log(9)]);
    transport.setEpoch("e2");
    FakeChannel.all[0]!.deliver([log(1)]);
    expect(seen).toEqual([9, 1]);
  });
});

describe("selectTransport", () => {
  it("uses the Tauri global when present and HTTP otherwise", () => {
    expect(selectTransport()).toBeInstanceOf(HttpTransport);
    (globalThis as { __TAURI__?: unknown }).__TAURI__ = { core: { invoke: vi.fn(), Channel: FakeChannel } };
    expect(selectTransport()).toBeInstanceOf(TauriTransport);
  });
});
