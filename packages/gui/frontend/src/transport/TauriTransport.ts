import { ApiError } from "./ApiError";
import { StreamRegistry, backoffDelay, type StreamEntry } from "./stream";
import type { Method, ServerFrame, StreamFilter, StreamHandlers, Subscription, Transport } from "./Transport";

/** The part of `window.__TAURI__` (withGlobalTauri) this transport uses; no npm dependency (D27). */
export interface TauriChannel<T = unknown> {
  onmessage: ((message: T) => void) | null;
}

export interface TauriGlobal {
  core: {
    invoke(command: string, args?: Record<string, unknown>): Promise<unknown>;
    Channel: new <T = unknown>() => TauriChannel<T>;
  };
}

export interface TauriTransportOptions {
  tauri?: TauriGlobal;
  setTimeout?: (callback: () => void, ms: number) => unknown;
  clearTimeout?: (handle: unknown) => void;
}

interface Live {
  entry: StreamEntry;
  channel: TauriChannel | null;
  remoteId: number | null;
  timer: unknown;
  attempt: number;
  started: boolean;
  closed: boolean;
}

export function tauriGlobal(): TauriGlobal | undefined {
  const candidate = (globalThis as { __TAURI__?: TauriGlobal }).__TAURI__;
  return candidate && candidate.core && typeof candidate.core.invoke === "function" ? candidate : undefined;
}

function malformed(): ApiError {
  return new ApiError(0, { code: "TRANSPORT_MALFORMED", message: "The desktop shell answered in an unexpected form" });
}

/** Desktop mode: requests through `invoke`, one Channel per subscription; the shell holds the secret and the socket. */
export class TauriTransport implements Transport {
  private readonly tauri: TauriGlobal;
  private readonly schedule: (callback: () => void, ms: number) => unknown;
  private readonly cancel: (handle: unknown) => void;
  private readonly entries = new StreamRegistry();
  private readonly live = new Map<string, Live>();

  constructor(options: TauriTransportOptions = {}) {
    const tauri = options.tauri ?? tauriGlobal();
    if (!tauri) throw new Error("window.__TAURI__ is not available");
    this.tauri = tauri;
    this.schedule = options.setTimeout ?? ((callback, ms) => setTimeout(callback, ms));
    this.cancel = options.clearTimeout ?? ((handle) => clearTimeout(handle as ReturnType<typeof setTimeout>));
  }

  setEpoch(epoch: string): void {
    this.entries.setEpoch(epoch);
  }

  async request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    if (!path.startsWith("/v1/") || path.includes("..")) throw new Error(`not an API path: ${path}`);
    const answer = await this.tauri.core.invoke("api_request", { method, path, body: body === undefined ? null : body });
    if (typeof answer !== "object" || answer === null || typeof (answer as { status?: unknown }).status !== "number") {
      throw malformed();
    }
    const { status, body: document } = answer as { status: number; body: unknown };
    if (status >= 400) throw ApiError.from(status, document);
    if (status < 200 || status >= 300) throw malformed();
    return document as T;
  }

  subscribe(filter: StreamFilter, handlers: StreamHandlers): Subscription {
    const entry = this.entries.add(filter, handlers);
    const live: Live = { entry, channel: null, remoteId: null, timer: null, attempt: 0, started: false, closed: false };
    this.live.set(entry.id, live);
    void this.open(live);
    return {
      close: () => {
        if (live.closed) return;
        live.closed = true;
        this.entries.remove(entry.id);
        this.live.delete(entry.id);
        this.detach(live);
        if (live.timer !== null) this.cancel(live.timer);
      },
    };
  }

  /** Stop listening on the current channel and tell the shell to drop its task. */
  private detach(live: Live): void {
    if (live.channel) live.channel.onmessage = null;
    live.channel = null;
    const id = live.remoteId;
    live.remoteId = null;
    if (id !== null) void this.tauri.core.invoke("api_unsubscribe", { id }).catch(() => undefined);
  }

  private async open(live: Live): Promise<void> {
    if (live.closed) return;
    const channel = new this.tauri.core.Channel();
    live.channel = channel;
    channel.onmessage = (message) => this.receive(live, channel, message);
    try {
      const id = await this.tauri.core.invoke("api_subscribe", { filter: live.entry.filter, channel });
      if (typeof id !== "number") throw malformed();
      if (live.closed || live.channel !== channel) {
        void this.tauri.core.invoke("api_unsubscribe", { id }).catch(() => undefined);
        return;
      }
      live.remoteId = id;
    } catch {
      if (live.channel === channel) this.lost(live, channel, false);
    }
  }

  /** The stream ended or could not start: resubscribe with backoff. The shell cannot resume, so the data is reloaded. */
  private lost(live: Live, channel: TauriChannel, wasStreaming: boolean): void {
    if (live.closed || live.channel !== channel) return;
    channel.onmessage = null;
    live.channel = null;
    live.remoteId = null;
    if (wasStreaming) live.started = true;
    const delay = backoffDelay(live.attempt);
    live.attempt += 1;
    live.timer = this.schedule(() => {
      live.timer = null;
      if (live.started) {
        live.entry.lastSeq = null;
        live.entry.handlers.onSnapshotRequired?.("cursor_expired");
      }
      void this.open(live);
    }, delay);
  }

  private receive(live: Live, channel: TauriChannel, message: unknown): void {
    if (live.closed || live.channel !== channel) return;
    const items = Array.isArray(message) ? message : [message];
    for (const item of items) {
      if (typeof item !== "object" || item === null) continue;
      if ("closed" in item) {
        this.lost(live, channel, true);
        return;
      }
      if ("dropped" in item) {
        live.entry.lastSeq = null;
        live.entry.handlers.onSnapshotRequired?.("overflow");
        continue;
      }
      if (typeof (item as { kind?: unknown }).kind !== "string") continue;
      live.attempt = 0;
      this.entries.deliver(live.entry, item as ServerFrame);
    }
  }
}
