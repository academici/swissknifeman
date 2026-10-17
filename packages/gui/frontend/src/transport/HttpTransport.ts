import { ApiError } from "./ApiError";
import { StreamRegistry, backoffDelay, type StreamEntry } from "./stream";
import type { Method, ServerFrame, StreamFilter, StreamHandlers, Subscription, Transport } from "./Transport";

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

/** Browser mode: same-origin fetch with the session cookie, and one WebSocket for every subscription. */
export class HttpTransport implements Transport {
  private readonly fetchImpl: typeof fetch;
  private readonly SocketImpl: new (url: string) => SocketLike;
  private readonly location: { protocol: string; host: string };
  private readonly schedule: (callback: () => void, ms: number) => unknown;
  private readonly entries = new StreamRegistry();
  private socket: SocketLike | null = null;
  private attempt = 0;
  private closedByUs = false;

  constructor(options: HttpTransportOptions = {}) {
    this.fetchImpl = options.fetch ?? ((...args) => fetch(...args));
    this.SocketImpl = options.WebSocket ?? (WebSocket as unknown as new (url: string) => SocketLike);
    this.location = options.location ?? window.location;
    this.schedule = options.setTimeout ?? ((callback, ms) => setTimeout(callback, ms));
  }

  setEpoch(epoch: string): void {
    this.entries.setEpoch(epoch);
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
    const entry = this.entries.add(filter, handlers);
    if (this.socket && this.socket.readyState === 1) this.sendSubscribe(entry);
    else this.connect();
    return {
      close: () => {
        if (!this.entries.remove(entry.id)) return;
        if (this.socket && this.socket.readyState === 1) {
          this.socket.send(JSON.stringify(this.entries.unsubscribeFrame(entry)));
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
      const delay = backoffDelay(this.attempt);
      this.attempt += 1;
      this.schedule(() => {
        if (!this.socket && this.entries.size > 0) this.connect();
      }, delay);
    };
    socket.onerror = () => undefined;
  }

  private sendSubscribe(entry: StreamEntry): void {
    this.socket?.send(JSON.stringify(this.entries.subscribeFrame(entry)));
  }

  private receive(data: unknown): void {
    let frame: ServerFrame;
    try {
      frame = JSON.parse(String(data)) as ServerFrame;
    } catch {
      return;
    }
    this.entries.dispatch(frame);
  }
}
