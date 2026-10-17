import type { ServerFrame, StreamFilter, StreamHandlers } from "./Transport";

export const STREAM_SCHEMA = "urn:swissknifeman:gui:stream:v1";
export const BACKOFF_MS = [500, 1000, 2000, 4000, 8000];

export function backoffDelay(attempt: number): number {
  return BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)] ?? 8000;
}

export interface StreamEntry {
  id: string;
  filter: StreamFilter;
  handlers: StreamHandlers;
  lastSeq: number | null;
}

/** Subscriptions of one transport and the seq/epoch/replay rules shared by every transport. */
export class StreamRegistry {
  private readonly items = new Map<string, StreamEntry>();
  private epoch: string | null = null;
  private counter = 0;

  get size(): number {
    return this.items.size;
  }

  values(): IterableIterator<StreamEntry> {
    return this.items.values();
  }

  get(id: string): StreamEntry | undefined {
    return this.items.get(id);
  }

  add(filter: StreamFilter, handlers: StreamHandlers): StreamEntry {
    this.counter += 1;
    const entry: StreamEntry = { id: `s${this.counter}`, filter, handlers, lastSeq: null };
    this.items.set(entry.id, entry);
    return entry;
  }

  remove(id: string): boolean {
    return this.items.delete(id);
  }

  /** A new epoch is another backend process: nothing can be resumed. */
  setEpoch(epoch: string): void {
    if (this.epoch !== null && this.epoch !== epoch) {
      for (const entry of this.items.values()) entry.lastSeq = null;
    }
    this.epoch = epoch;
  }

  /** What a (re)subscribe sends: the last seq and the epoch it belongs to, or nulls for a fresh start. */
  resume(entry: StreamEntry): { cursor: number | null; epoch: string | null } {
    const resume = entry.lastSeq !== null && this.epoch !== null;
    return { cursor: resume ? entry.lastSeq : null, epoch: resume ? this.epoch : null };
  }

  subscribeFrame(entry: StreamEntry): Record<string, unknown> {
    return { $schema: STREAM_SCHEMA, kind: "subscribe", id: entry.id, filter: entry.filter, ...this.resume(entry) };
  }

  unsubscribeFrame(entry: StreamEntry): Record<string, unknown> {
    return { $schema: STREAM_SCHEMA, kind: "unsubscribe", id: entry.id };
  }

  /** A frame routed by its `sub` field (one socket for all subscriptions). */
  dispatch(frame: ServerFrame): void {
    if (frame.kind === "heartbeat") return;
    const entry = "sub" in frame && frame.sub ? this.items.get(frame.sub) : undefined;
    if (entry) this.deliver(entry, frame);
  }

  /** A frame already known to belong to `entry`: snapshot reset, errors, and each seq at most once. */
  deliver(entry: StreamEntry, frame: ServerFrame): void {
    if (frame.kind === "heartbeat") return;
    if (frame.kind === "snapshot_required") {
      entry.lastSeq = null;
      entry.handlers.onSnapshotRequired?.(frame.reason);
      return;
    }
    if (frame.kind === "error") {
      entry.handlers.onError?.(frame);
      return;
    }
    if (entry.lastSeq !== null && frame.seq <= entry.lastSeq) return; // already applied
    entry.lastSeq = frame.seq;
    entry.handlers.onFrame(frame);
  }
}
