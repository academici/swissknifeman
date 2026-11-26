import { version as packageVersion } from "../../package.json";
import { tokenStore } from "../features/auth/tokenStore";
import { applyAuthHeaders, type AuthMaterial } from "./authMaterial";
import { ApiError } from "./errors";
import type { EventEnvelope } from "./generated/kernel";
import type { SessionEvent } from "./generated/runtimes";
import { subscribeAttempt } from "./live";
import { trackSubscription } from "./streamRegistry";
import { EventStream, parseEventCursor, type EventStreamHandlers } from "./stream";

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RequestOptions {
  body?: unknown;
  ifMatch?: string;
  ifNoneMatch?: string;
  idempotencyKey?: string;
  expectedDigest?: string;
  contentType?: "application/json" | "application/merge-patch+json" | "application/octet-stream";
  responseType?: "blob";
  signal?: AbortSignal;
  raw?: Blob;
}

export interface Response<T> {
  data: T;
  etag: string | null;
  requestId: string;
  replayed: boolean;
  eventsCursor?: number;
  notModified?: true;
}

export interface EventFilter {
  workspaceId: string;
  after?: number;
  types?: readonly string[];
  streams?: readonly string[];
}

export interface StreamHandlers<T = EventEnvelope> {
  onEvent(event: T): void;
  onError?(error: ApiError): void;
}

export type LiveHandlers = StreamHandlers<SessionEvent>;

export interface Subscription {
  close(): void;
}

export interface Transport {
  request<T>(method: Method, path: string, options?: RequestOptions): Promise<Response<T>>;
  events(filter: EventFilter, handlers: EventStreamHandlers): Subscription;
  live(attemptId: string, handlers: LiveHandlers): Subscription;
}

type Streams = Pick<Transport, "events" | "live">;

interface HttpTransportOptions {
  fetch?: typeof fetch;
  getToken?: () => string | null;
  getAuth?: () => AuthMaterial;
  onUnauthorized?: () => void;
  onForbidden?: () => void;
  clientVersion?: string;
  streams?: Streams;
}

function assertRelativePath(path: string): void {
  if (!path.startsWith("/") || /[\s\\#\p{Cc}]/u.test(path)) {
    throw new TypeError("Expected a same-origin request path");
  }
  let pathname = path.split("?", 1)[0] ?? "";
  // Browsers normalize encoded dot segments. Also reject separators or dots
  // hidden behind percent escapes that an intermediary could decode again.
  for (;;) {
    if (pathname.startsWith("//") || pathname.includes("..") || pathname.includes("\\")) {
      throw new TypeError("Expected a same-origin request path without traversal");
    }
    const decoded = pathname.replace(/%(?:25|2e|2f|5c)/giu, (escape) => String.fromCharCode(parseInt(escape.slice(1), 16)));
    if (decoded === pathname) return;
    pathname = decoded;
  }
}

function throwNetworkFailure(error: unknown, requestId: string, path: string, signal?: AbortSignal): never {
  const aborted = typeof error === "object" && error !== null && "name" in error && error.name === "AbortError";
  if (signal?.aborted || aborted) throw error;
  throw ApiError.unavailable(requestId, path);
}

async function readBody<T>(read: () => Promise<T>, requestId: string, path: string, signal?: AbortSignal): Promise<T> {
  try {
    return await read();
  } catch (error) {
    throwNetworkFailure(error, requestId, path, signal);
  }
}

async function readJson(response: globalThis.Response, requestId: string, path: string, signal?: AbortSignal): Promise<unknown> {
  const body = await readBody(() => response.text(), requestId, path, signal);
  try {
    return JSON.parse(body);
  } catch (error) {
    if (!response.ok && error instanceof SyntaxError) return null;
    throw error;
  }
}

export class HttpTransport implements Transport {
  constructor(private readonly options: HttpTransportOptions = {}) {}

  private material(): AuthMaterial {
    if (this.options.getAuth) return this.options.getAuth();
    return { mode: "token", token: (this.options.getToken ?? tokenStore.get)(), csrfToken: null };
  }

  async request<T>(method: Method, path: string, options: RequestOptions = {}): Promise<Response<T>> {
    assertRelativePath(path);
    if (options.raw !== undefined && options.body !== undefined) {
      throw new TypeError("Provide either a structured body or raw bytes");
    }

    const outgoingId = `web-${crypto.randomUUID()}`;
    const headers = new Headers({
      Accept: options.responseType === "blob" ? "*/*" : "application/json, application/problem+json",
      "X-Request-Id": outgoingId,
      "SKM-Client-Version": this.options.clientVersion ?? packageVersion,
    });
    const credentials = applyAuthHeaders(headers, method, this.material());
    if (options.ifMatch !== undefined) headers.set("If-Match", options.ifMatch);
    if (options.ifNoneMatch !== undefined) headers.set("If-None-Match", options.ifNoneMatch);
    if (options.idempotencyKey !== undefined) headers.set("Idempotency-Key", options.idempotencyKey);
    if (options.expectedDigest !== undefined) headers.set("SKM-Expected-Digest", options.expectedDigest);

    const request: RequestInit = { method, headers, credentials, redirect: "error" };
    if (options.signal !== undefined) request.signal = options.signal;
    const body = options.raw ?? options.body;
    const formData = body instanceof FormData;
    const blob = body instanceof Blob;
    if (options.contentType !== undefined) {
      headers.set("Content-Type", options.contentType);
    } else if (options.raw !== undefined || (blob && !body.type)) {
      headers.set("Content-Type", "application/octet-stream");
    } else if (!formData && !blob && (method !== "GET" || body !== undefined)) {
      headers.set("Content-Type", "application/json");
    }
    if (formData || blob) request.body = body;
    else if (body !== undefined) request.body = JSON.stringify(body) ?? null;

    let response: globalThis.Response;
    try {
      response = await (this.options.fetch ?? fetch)(path, request);
    } catch (error) {
      throwNetworkFailure(error, outgoingId, path, options.signal);
    }

    const requestId = response.headers.get("X-Request-Id") ?? outgoingId;
    const notModified = response.status === 304 && method === "GET" && options.ifNoneMatch !== undefined;
    if (!response.ok && !notModified) {
      if (response.status === 401) this.options.onUnauthorized?.();
      if (response.status === 403) this.options.onForbidden?.();
      const type = response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase();
      const problem: unknown = type === "application/problem+json"
        ? await readJson(response, requestId, path, options.signal)
        : null;
      throw ApiError.fromResponse(response.status, problem, requestId, path);
    }

    let data: unknown;
    if (!notModified && response.status !== 204 && response.status !== 205) {
      data = options.responseType === "blob"
        ? await readBody(() => response.blob(), requestId, path, options.signal)
        : await readJson(response, requestId, path, options.signal);
    }
    const eventsCursor = method === "GET" ? parseEventCursor(response.headers.get("SKM-Events-Cursor")) : null;
    return {
      data: data as T,
      etag: response.headers.get("ETag"),
      requestId,
      replayed: response.headers.get("Idempotency-Replayed") === "true",
      ...(eventsCursor === null ? {} : { eventsCursor }),
      ...(notModified ? { notModified: true } : {}),
    };
  }

  events(filter: EventFilter, handlers: EventStreamHandlers): Subscription {
    if (this.options.streams) return trackSubscription(this.options.streams.events(filter, handlers));
    return trackSubscription(new EventStream(filter, handlers, {
      ...(this.options.fetch ? { fetch: this.options.fetch } : {}),
      ...(this.options.clientVersion ? { clientVersion: this.options.clientVersion } : {}),
      ...(this.options.onUnauthorized ? { onUnauthorized: this.options.onUnauthorized } : {}),
      getAuth: () => this.material(),
    }));
  }

  live(attemptId: string, handlers: LiveHandlers): Subscription {
    if (this.options.streams) return trackSubscription(this.options.streams.live(attemptId, handlers));
    const material = this.material();
    return subscribeAttempt(attemptId, {
      token: material.mode === "token" ? material.token : null,
      credentials: material.mode === "token" ? "omit" : "include",
    }, {
      onEvent: (event) => handlers.onEvent(event),
      onGap: () => undefined,
      onEnd: () => undefined,
      onError: (error) => {
        if (error instanceof ApiError) handlers.onError?.(error);
      },
      onUnauthorized: () => this.options.onUnauthorized?.(),
      onConnection: () => undefined,
    });
  }
}
