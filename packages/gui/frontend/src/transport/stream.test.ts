import { describe, expect, it } from "vitest";
import { StreamRegistry, backoffDelay } from "./stream";
import type { ServerFrame } from "./Transport";

const log = (seq: number, sub = "s1") =>
  ({ kind: "log", seq, sub, run_id: `run-${"a".repeat(32)}`, stream: "stdout", chunk: seq, text: "x", truncated: false }) as unknown as ServerFrame;

describe("StreamRegistry", () => {
  it("numbers subscriptions and delivers each seq once, in order", () => {
    const registry = new StreamRegistry();
    const seen: number[] = [];
    const entry = registry.add({}, { onFrame: (frame) => seen.push(frame.seq) });
    expect(entry.id).toBe("s1");
    registry.dispatch(log(3));
    registry.dispatch(log(3));
    registry.dispatch(log(2));
    registry.dispatch(log(4));
    registry.dispatch(log(9, "s7"));
    registry.dispatch({ kind: "heartbeat", seq: 5, at: "t" } as unknown as ServerFrame);
    expect(seen).toEqual([3, 4]);
  });

  it("resumes only inside one epoch", () => {
    const registry = new StreamRegistry();
    const entry = registry.add({}, { onFrame: () => undefined });
    expect(registry.resume(entry)).toEqual({ cursor: null, epoch: null });
    registry.setEpoch("e1");
    registry.dispatch(log(5));
    expect(registry.subscribeFrame(entry)).toMatchObject({ kind: "subscribe", id: "s1", cursor: 5, epoch: "e1" });
    registry.setEpoch("e1");
    expect(registry.resume(entry).cursor).toBe(5);
    registry.setEpoch("e2");
    expect(registry.resume(entry)).toEqual({ cursor: null, epoch: null });
  });

  it("snapshot_required resets the cursor; errors go to onError; remove forgets", () => {
    const registry = new StreamRegistry();
    const reasons: string[] = [];
    const errors: unknown[] = [];
    const entry = registry.add({}, { onFrame: () => undefined, onSnapshotRequired: (r) => reasons.push(r), onError: (f) => errors.push(f) });
    registry.dispatch(log(5));
    registry.dispatch({ kind: "snapshot_required", sub: "s1", reason: "overflow" } as unknown as ServerFrame);
    expect(entry.lastSeq).toBeNull();
    registry.dispatch({ kind: "error", sub: "s1" } as unknown as ServerFrame);
    expect(reasons).toEqual(["overflow"]);
    expect(errors).toHaveLength(1);
    expect(registry.remove("s1")).toBe(true);
    expect(registry.remove("s1")).toBe(false);
    expect(registry.size).toBe(0);
  });

  it("backs off 0.5 s .. 8 s", () => {
    expect([0, 1, 4, 9].map(backoffDelay)).toEqual([500, 1000, 8000, 8000]);
  });
});
