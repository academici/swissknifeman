import type { ErrorFrame, EventFrame, HeartbeatFrame, LogFrame, RunFrame, SnapshotFrame } from "../contracts";

export type Method = "GET" | "POST" | "PATCH";

/** What a subscription selects; every key given must match (stream/v1 `subscribe.filter`). */
export interface StreamFilter {
  projects?: string[];
  runs?: string[];
  owners?: string[];
  types?: string[];
}

export type ServerFrame = EventFrame | LogFrame | RunFrame | HeartbeatFrame | SnapshotFrame | ErrorFrame;

export interface StreamHandlers {
  /** A frame of this subscription (each seq at most once, in order). */
  onFrame(frame: EventFrame | LogFrame | RunFrame): void;
  /** The backend could not replay what was missed: reload the data, live frames follow. */
  onSnapshotRequired?(reason: "cursor_expired" | "overflow"): void;
  onError?(frame: ErrorFrame): void;
}

export interface Subscription {
  close(): void;
}

/**
 * The only way the UI talks to the backend. Browser mode: HTTP + WebSocket on loopback (HttpTransport); the desktop
 * shell later brings a Tauri implementation with the same interface. The UI sends typed bodies only (I2).
 */
export interface Transport {
  request<T>(method: Method, path: string, body?: unknown): Promise<T>;
  subscribe(filter: StreamFilter, handlers: StreamHandlers): Subscription;
  /** The backend epoch from /v1/bootstrap; a reconnect resumes from the last seq only within it. */
  setEpoch(epoch: string): void;
}
