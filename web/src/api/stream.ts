import { version as packageVersion } from "../../package.json";
import type { QueryClient } from "@tanstack/react-query";
import { applyAuthHeaders, type AuthMaterial } from "./authMaterial";
import { ApiError } from "./errors";
import type { EventEnvelope } from "./generated/kernel";
import type { EventFilter, Response as ApiResponse, StreamHandlers, Subscription, Transport } from "./transport";

const minDelay = 1_000;
const maxDelay = 30_000;

export async function readWithEvents<T>(
  read: (() => Promise<ApiResponse<T>>) | { transport: Transport; path: string },
  signal?: AbortSignal,
  acceptCursor?: (cursor: number | undefined) => boolean,
): Promise<ApiResponse<T>> {
  for (;;) {
    signal?.throwIfAborted();
    const response = typeof read === "function"
      ? await read()
      : await read.transport.request<T>("GET", read.path, signal === undefined ? undefined : { signal });
    signal?.throwIfAborted();
    if (acceptCursor?.(response.eventsCursor) ?? true) return response;
  }
}

export function parseEventCursor(value: string | null): number | null {
  if (value === null || !/^\d+$/u.test(value)) return null;
  const cursor = Number(value);
  return Number.isSafeInteger(cursor) ? cursor : null;
}

interface Frame {
  id: string | null;
  event: string;
  data: string;
}

class SseParser {
  private pending = "";
  private skipLf = false;
  private id: string | null = null;
  private event = "";
  private data: string[] = [];

  constructor(
    private readonly dispatch: (frame: Frame) => void,
    private readonly retry: (ms: number) => void,
  ) {}

  push(chunk: string): void {
    if (!chunk) return;
    const offset = this.skipLf && chunk.startsWith("\n") ? 1 : 0;
    let start = offset;
    this.skipLf = chunk.endsWith("\r");
    for (const match of chunk.slice(offset).matchAll(/\r\n?|\n/gu)) {
      const end = match.index + offset;
      this.line(this.pending + chunk.slice(start, end));
      this.pending = "";
      start = end + match[0].length;
    }
    this.pending += chunk.slice(start);
  }

  private line(line: string): void {
    if (line === "") {
      if (this.data.length) {
        this.dispatch({ id: this.id, event: this.event || "message", data: this.data.join("\n") });
      }
      this.id = null;
      this.event = "";
      this.data = [];
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /u, "");
    switch (field) {
      case "id":
        if (!value.includes("\u0000")) this.id = value;
        break;
      case "event":
        this.event = value;
        break;
      case "data":
        this.data.push(value);
        break;
      case "retry": {
        const ms = parseEventCursor(value);
        if (ms !== null) this.retry(Math.max(minDelay, ms));
        break;
      }
    }
  }
}

export interface EventStreamHandlers extends StreamHandlers {
  onCursor?(cursor: number): void;
  onConnectionChange?(connected: boolean): void;
  onStopped?(): void;
  onSnapshotRequired?(): void;
  queryClient?: Pick<QueryClient, "invalidateQueries">;
}

interface EventStreamOptions {
  fetch?: typeof fetch;
  getToken?: () => string | null;
  getAuth?: () => AuthMaterial;
  onUnauthorized?: () => void;
  clientVersion?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function decodeEvent(data: string, workspaceId: string): EventEnvelope | null {
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return null;
  }
  if (!isRecord(value) || value.workspace_id !== workspaceId ||
      typeof value.type !== "string" || typeof value.stream_id !== "string" ||
      typeof value.stream_kind !== "string" || !isRecord(value.payload) ||
      ["principal", "host", "pack", "runtime"].includes(value.stream_kind)) return null;
  return value as unknown as EventEnvelope;
}

function eventPath(filter: EventFilter, after?: number): string {
  const params = new URLSearchParams({ workspace_id: filter.workspaceId });
  if (after !== undefined) params.set("after", String(after));
  for (const stream of filter.streams ?? []) params.append("stream", stream);
  if (filter.types?.length) params.set("types", filter.types.join(","));
  return `/api/v1/events?${params}`;
}

async function responseError(response: Response, requestId: string, path: string): Promise<ApiError> {
  const type = response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (type !== "application/problem+json") void response.body?.cancel().catch(() => undefined);
  const problem: unknown = type === "application/problem+json" ? await response.json().catch(() => null) : null;
  return ApiError.fromResponse(response.status, problem, response.headers.get("X-Request-Id") ?? requestId, path);
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", done, { once: true });
  });
}

export class EventStream implements Subscription {
  private readonly controller = new AbortController();
  private lastCursor: number | null;
  private retryDelay = minDelay;
  private failures = 0;

  constructor(
    private readonly filter: EventFilter,
    private readonly handlers: EventStreamHandlers,
    private readonly options: EventStreamOptions = {},
  ) {
    this.lastCursor = filter.after ?? null;
    void this.run();
  }

  get cursor(): number | null {
    return this.lastCursor;
  }

  close(): void {
    this.controller.abort();
  }

  private material(): AuthMaterial {
    if (this.options.getAuth) return this.options.getAuth();
    return { mode: "token", token: this.options.getToken?.() ?? null, csrfToken: null };
  }

  private frame = ({ id, event, data }: Frame): void => {
    if (this.controller.signal.aborted) return;
    const cursor = parseEventCursor(id);
    const advances = cursor !== null && (this.lastCursor === null || cursor > this.lastCursor);
    if (event === "snapshot-required") {
      if (advances) this.advance(cursor);
      void this.handlers.queryClient?.invalidateQueries();
      this.handlers.onSnapshotRequired?.();
    } else if (advances) {
      if (event === "cursor") {
        this.advance(cursor);
        return;
      }
      const envelope = decodeEvent(data, this.filter.workspaceId);
      if (envelope !== null) {
        this.advance(cursor);
        this.handlers.onEvent(envelope);
      }
    }
  };

  private advance(cursor: number): void {
    this.lastCursor = cursor;
    this.handlers.onCursor?.(cursor);
  }

  private async read(body: ReadableStream<Uint8Array>, signal: AbortSignal): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    const parser = new SseParser(this.frame, (ms) => { this.retryDelay = ms; });
    const cancel = () => { void reader.cancel().catch(() => undefined); };
    signal.addEventListener("abort", cancel, { once: true });
    try {
      if (signal.aborted) cancel();
      while (!signal.aborted) {
        const { value, done } = await reader.read();
        if (done) {
          parser.push(decoder.decode());
          return;
        }
        parser.push(decoder.decode(value, { stream: true }));
      }
    } finally {
      signal.removeEventListener("abort", cancel);
      reader.releaseLock();
    }
  }

  private async run(): Promise<void> {
    const signal = this.controller.signal;
    const resumePath = eventPath(this.filter);
    let path = this.filter.after === undefined ? resumePath : eventPath(this.filter, this.filter.after);
    while (!signal.aborted) {
      const retry = await this.connect(path, signal);
      if (!retry || signal.aborted) return;
      path = resumePath;
      const delay = Math.min(maxDelay, Math.max(this.retryDelay, minDelay * 2 ** this.failures));
      this.failures += 1;
      await wait(delay, signal);
    }
  }

  private async connect(path: string, signal: AbortSignal): Promise<boolean> {
    const requestId = `web-${crypto.randomUUID()}`;
    const headers = new Headers({
      Accept: "text/event-stream",
      "X-Request-Id": requestId,
      "SKM-Client-Version": this.options.clientVersion ?? packageVersion,
    });
    const credentials = applyAuthHeaders(headers, "GET", this.material());
    if (this.lastCursor !== null) headers.set("Last-Event-ID", String(this.lastCursor));

    let response: Response;
    try {
      response = await (this.options.fetch ?? fetch)(path, {
        method: "GET", headers, signal, credentials, redirect: "error",
      });
    } catch {
      if (!signal.aborted) this.handlers.onError?.(ApiError.unavailable(requestId, path));
      return true;
    }
    if (signal.aborted) {
      void response.body?.cancel().catch(() => undefined);
      return false;
    }
    if (response.status !== 200) {
      const error = await responseError(response, requestId, path);
      if (signal.aborted) return false;
      const retryable = response.status === 503 || response.status === 429;
      if (!retryable) this.handlers.onStopped?.();
      if (response.status === 401) this.options.onUnauthorized?.();
      this.handlers.onError?.(error);
      return retryable;
    }
    this.failures = 0;
    this.handlers.onConnectionChange?.(true);
    try {
      if (response.body) await this.read(response.body, signal);
    } catch {
      if (!signal.aborted) this.handlers.onError?.(ApiError.unavailable(requestId, path));
    } finally {
      if (!signal.aborted) this.handlers.onConnectionChange?.(false);
    }
    return true;
  }
}
