import { ApiError } from "./ApiError";
import type { Method, ServerFrame, StreamFilter, StreamHandlers, Subscription, Transport } from "./Transport";

const STREAM = "urn:swissknifeman:gui:stream:v1";
const BACKOFF_MS = [500, 1000, 2000, 4000, 8000];

interface SocketLike {
  readyState: number;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  send(data: string): void;
  close(): void;
}

export interface HttpTransportOptions {
  fetch?: typeof fetch;
  WebSocket?: new (url: string) => SocketLike;
  location?: { protocol: string; host: string };
  setTimeout?: (callback: () => void, ms: number) => unknown;
}

interface Entry {
  id: string;
  filter: StreamFilter;
  handlers: StreamHandlers;
  lastSeq: number | null;
}

/** Browser mode: same-origin fetch with the session cookie, and one WebSocket for every subscription. */
export class HttpTransport implements Transport {
  private readonly fetchImpl: typeof fetch;
  private readonly SocketImpl: new (url: string) => SocketLike;
  private readonly location: { protocol: string; host: string };
  private readonly schedule: (callback: () => void, ms: number) => unknown;
  private readonly entries = new Map<string, Entry>();
  private socket: SocketLike | null = null;
  private epoch: string | null = null;
  private attempt = 0;
  private counter = 0;
  private closedByUs = false;

  constructor(options: HttpTransportOptions = {}) {
    this.fetchImpl = options.fetch ?? ((...args) => fetch(...args));
    this.SocketImpl = options.WebSocket ?? (WebSocket as unknown as new (url: string) => SocketLike);
    this.location = options.location ?? window.location;
    this.schedule = options.setTimeout ?? ((callback, ms) => setTimeout(callback, ms));
  }

  setEpoch(epoch: string): void {
    if (this.epoch !== null && this.epoch !== epoch) {
      for (const entry of this.entries.values()) entry.lastSeq = null; // another backend process: no resume
    }
    this.epoch = epoch;
  }

  async request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    if (!path.startsWith("/v1/") || path.includes("..")) throw new Error(`not an API path: ${path}`);
    const response = await this.fetchImpl(path, {
      method,
      credentials: "same-origin",
      headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    let document: unknown;
    try {
      document = text ? JSON.parse(text) : null;
    } catch {
      document = null;
    }
    if (!response.ok) throw ApiError.from(response.status, document);
    return document as T;
  }

  subscribe(filter: StreamFilter, handlers: StreamHandlers): Subscription {
    this.counter += 1;
    const entry: Entry = { id: `s${this.counter}`, filter, handlers, lastSeq: null };
    this.entries.set(entry.id, entry);
    if (this.socket && this.socket.readyState === 1) this.sendSubscribe(entry);
    else this.connect();
    return {
      close: () => {
        if (!this.entries.delete(entry.id)) return;
        if (this.socket && this.socket.readyState === 1) {
          this.socket.send(JSON.stringify({ $schema: STREAM, kind: "unsubscribe", id: entry.id }));
        }
        if (this.entries.size === 0 && this.socket) {
          this.closedByUs = true;
          this.socket.close();
          this.socket = null;
        }
      },
    };
  }

  private connect(): void {
    if (this.socket) return;
    const scheme = this.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new this.SocketImpl(`${scheme}//${this.location.host}/v1/events`);
    this.socket = socket;
    this.closedByUs = false;
    socket.onopen = () => {
      this.attempt = 0;
      for (const entry of this.entries.values()) this.sendSubscribe(entry);
    };
    socket.onmessage = (event) => this.receive(event.data);
    socket.onclose = () => {
      if (this.socket === socket) this.socket = null;
      if (this.closedByUs || this.entries.size === 0) return;
      const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)] ?? 8000;
      this.attempt += 1;
      this.schedule(() => {
        if (!this.socket && this.entries.size > 0) this.connect();
      }, delay);
    };
    socket.onerror = () => undefined;
  }

  private sendSubscribe(entry: Entry): void {
    const resume = entry.lastSeq !== null && this.epoch !== null;
    this.socket?.send(
      JSON.stringify({
        $schema: STREAM,
        kind: "subscribe",
        id: entry.id,
        filter: entry.filter,
        cursor: resume ? entry.lastSeq : null,
        epoch: resume ? this.epoch : null,
      }),
    );
  }

  private receive(data: unknown): void {
    let frame: ServerFrame;
    try {
      frame = JSON.parse(String(data)) as ServerFrame;
    } catch {
      return;
    }
    if (frame.kind === "heartbeat") return;
    const entry = "sub" in frame && frame.sub ? this.entries.get(frame.sub) : undefined;
    if (!entry) return;
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
