import { ApiError } from "./errors";
import type { SessionEvent } from "./generated/runtimes";
import { trackSubscription } from "./streamRegistry";
import type { Subscription } from "./transport";

export interface LiveGap {
  reason: "buffer_missing" | "buffer_evicted";
  after: number;
  oldest: number | null;
}

interface AttemptFeed {
  onEvent(event: SessionEvent): void;
  onGap(gap: LiveGap): void;
  onEnd(): void;
  onError(error: Error): void;
  onUnauthorized(): void;
  onConnection(connected: boolean): void;
}

type LiveFrame = { type: "end" } | { type: "gap"; id: number; gap: LiveGap }
  | { type: "session"; id: number; event: SessionEvent };

// Frame IDs belong to the API process's attempt buffer. SessionEvent.seq can restart between steps.
function decode(frame: string): LiveFrame | null {
  let name = "";
  let id: number | undefined;
  const data: string[] = [];
  for (const line of frame.split(/\r?\n/u)) {
    const colon = line.indexOf(":");
    if (colon <= 0) continue;
    const value = line.slice(colon + 1).replace(/^ /u, "");
    switch (line.slice(0, colon)) {
      case "event": name = value; break;
      case "id": if (/^\d+$/u.test(value)) id = Number(value); break;
      case "data": data.push(value); break;
    }
  }
  if (!data.length) return null; // includes heartbeat comments
  if (name === "end") return { type: "end" };
  if (id === undefined || !Number.isSafeInteger(id)) throw new SyntaxError("Некорректный курсор потока");
  const payload = JSON.parse(data.join("\n"));
  if (name === "gap" && (payload?.reason === "buffer_missing" || payload?.reason === "buffer_evicted") &&
      Number.isSafeInteger(payload.after) && (payload.oldest === null || Number.isSafeInteger(payload.oldest))) {
    return { type: "gap", id, gap: payload };
  }
  if (payload?.type !== name || id < 1) throw new SyntaxError("Некорректное событие потока");
  return { type: "session", id, event: payload };
}

async function* frames(body: ReadableStream<Uint8Array>, signal: AbortSignal) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  signal.addEventListener("abort", cancel, { once: true });
  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) return; // A partial frame will be replayed from the last complete ID.
      const parts = (pending + decoder.decode(value, { stream: true })).split(/\r?\n\r?\n/u);
      pending = parts.pop() ?? "";
      for (const part of parts) {
        const frame = decode(part);
        if (frame) yield frame;
      }
    }
  } finally {
    signal.removeEventListener("abort", cancel);
    cancel();
    reader.releaseLock();
  }
}

export interface LiveAuth {
  token: string | null;
  credentials?: RequestCredentials;
}

export function subscribeAttempt(attemptId: string, tokenOrAuth: string | LiveAuth, feed: AttemptFeed): Subscription {
  const auth: LiveAuth = typeof tokenOrAuth === "string"
    ? { token: tokenOrAuth, credentials: "omit" }
    : tokenOrAuth;
  const credentials = auth.credentials ?? (auth.token ? "omit" : "include");
  const path = "/api/v1/attempts/" + encodeURIComponent(attemptId) + "/live";
  const controller = new AbortController();
  const { signal } = controller;
  let cursor: number | null = null;
  let delay = 1000;
  let retry: ReturnType<typeof setTimeout> | undefined;

  async function connect() {
    const requestId = "web-" + crypto.randomUUID();
    try {
      const headers = new Headers({
        Accept: "text/event-stream", "X-Request-Id": requestId,
      });
      if (auth.token) headers.set("Authorization", "Bearer " + auth.token);
      if (cursor !== null) headers.set("Last-Event-ID", String(cursor));
      const response = await fetch(path, { headers, signal, credentials, redirect: "error" });
      signal.throwIfAborted();
      if (!response.ok) {
        if (response.status === 401) {
          controller.abort();
          feed.onUnauthorized();
          return;
        }
        const problem = await response.json().catch(() => null);
        throw ApiError.fromResponse(response.status, problem, response.headers.get("X-Request-Id") ?? requestId, path);
      }
      if (!response.body || response.headers.get("Content-Type")?.split(";")[0] !== "text/event-stream") {
        throw new SyntaxError("Ожидался поток событий попытки");
      }
      feed.onConnection(true);
      for await (const frame of frames(response.body, signal)) {
        if (signal.aborted) return;
        if (frame.type === "end") { feed.onEnd(); return; }
        if (frame.type === "gap") feed.onGap(frame.gap);
        else if (cursor === null || frame.id > cursor) feed.onEvent(frame.event);
        else continue;
        cursor = frame.id;
        delay = 1000;
      }
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof SyntaxError || (error instanceof ApiError && error.status < 500)) {
        feed.onError(error);
        return;
      }
    }
    if (signal.aborted) return;
    feed.onConnection(false);
    retry = setTimeout(() => { void connect(); }, delay);
    delay = Math.min(30_000, delay * 2);
  }

  void connect();
  return trackSubscription({ close() { clearTimeout(retry); controller.abort(); } });
}
