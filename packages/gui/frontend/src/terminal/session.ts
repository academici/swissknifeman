// Client of the terminal WebSocket `/v1/terminal/{id}/io` (contract terminal/v1; the REST documents are generated, the
// JSON frames of the socket live in `$defs` of the contract and are not generated, so they are typed here).
//
// Backpressure: the server reads the PTY only while it holds credit. The client grants a window at the start and
// returns credit for bytes only after xterm has written them (the callback of `term.write`), in batches of at
// least window/4 and always before `exit`, so a slow terminal slows the shell down and nothing is dropped.

export type ClientFrame =
  | { t: "input"; data: string }
  | { t: "resize"; cols: number; rows: number }
  | { t: "credit"; bytes: number };

export type EndReason = "exit" | "closed" | "idle" | "max" | "backend_stop" | "error";

export type ServerFrame =
  | { t: "output"; seq: number; data: string }
  | { t: "exit"; code: number; signal?: number; reason: EndReason }
  | { t: "error"; code: string; message: string };

/** The unpaid credit of a client is capped at 4 * credit_bytes and credit_bytes is at least 4096: 16384 always fits. */
export const CREDIT_WINDOW = 16384;
/** A frame of input carries at most 64 KiB of bytes; larger input is cut into pieces of this size. */
export const INPUT_PIECE = 32 * 1024;

export type SessionState = "connecting" | "open" | "exited" | "closed" | "failed";

export interface SocketLike {
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  send(data: string): void;
  close(): void;
}

export interface SessionHandlers {
  /** Output bytes; call `written` once the terminal has taken them (this returns the credit). */
  onOutput(bytes: Uint8Array, written: () => void): void;
  onExit(info: { code: number; signal?: number; reason: EndReason }): void;
  onError(code: string, message: string): void;
  onState(state: SessionState): void;
}

export interface SessionOptions {
  sessionId: string;
  handlers: SessionHandlers;
  socketFactory?: (url: string) => SocketLike;
  location?: { protocol: string; host: string };
  window?: number;
}

export function terminalUrl(sessionId: string, location: { protocol: string; host: string }): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/v1/terminal/${encodeURIComponent(sessionId)}/io`;
}

export function toBase64(bytes: Uint8Array): string {
  let text = "";
  for (let at = 0; at < bytes.length; at += 8192) text += String.fromCharCode(...bytes.subarray(at, at + 8192));
  return btoa(text);
}

export function fromBase64(data: string): Uint8Array {
  const text = atob(data);
  const bytes = new Uint8Array(text.length);
  for (let at = 0; at < text.length; at += 1) bytes[at] = text.charCodeAt(at);
  return bytes;
}

export class TerminalSession {
  state: SessionState = "connecting";
  private readonly socket: SocketLike;
  private readonly window: number;
  private owed = 0;
  private ended = false;
  private lastSize: string | null = null;

  constructor(private readonly options: SessionOptions) {
    this.window = options.window ?? CREDIT_WINDOW;
    const url = terminalUrl(options.sessionId, options.location ?? window.location);
    this.socket = options.socketFactory ? options.socketFactory(url) : (new WebSocket(url) as unknown as SocketLike);
    this.socket.onopen = () => {
      this.send({ t: "credit", bytes: this.window }); // the first credit comes at once
      this.setState("open");
    };
    this.socket.onmessage = (event) => this.receive(event.data);
    this.socket.onerror = () => {
      if (!this.ended) this.finish("failed");
    };
    this.socket.onclose = () => {
      if (!this.ended) this.finish("closed");
    };
  }

  sendInput(data: string | Uint8Array): void {
    if (this.state !== "open") return;
    const bytes = typeof data === "string" ? new TextEncoder().encode(data) : data;
    for (let at = 0; at < bytes.length; at += INPUT_PIECE) {
      this.send({ t: "input", data: toBase64(bytes.subarray(at, at + INPUT_PIECE)) });
    }
  }

  /** Tell the server the size; the same size twice is sent once. */
  sendResize(cols: number, rows: number): void {
    if (this.state !== "open") return;
    const key = `${cols}x${rows}`;
    if (key === this.lastSize) return;
    this.lastSize = key;
    this.send({ t: "resize", cols, rows });
  }

  /** Close the socket; the server ends the session when the socket goes away. */
  close(): void {
    if (!this.ended) this.finish("closed");
  }

  private setState(state: SessionState): void {
    this.state = state;
    this.options.handlers.onState(state);
  }

  private finish(state: SessionState): void {
    this.ended = true;
    this.socket.onopen = this.socket.onmessage = this.socket.onclose = this.socket.onerror = null;
    try {
      this.socket.close();
    } catch {
      // already closed
    }
    if (this.state !== "exited") this.setState(state);
  }

  private send(frame: ClientFrame): void {
    this.socket.send(JSON.stringify(frame));
  }

  private flush(): void {
    if (this.owed > 0 && !this.ended) {
      const bytes = this.owed;
      this.owed = 0;
      this.send({ t: "credit", bytes });
    }
  }

  private receive(raw: unknown): void {
    if (typeof raw !== "string") return;
    let frame: ServerFrame;
    try {
      frame = JSON.parse(raw) as ServerFrame;
    } catch {
      return;
    }
    if (frame.t === "output") {
      const bytes = fromBase64(frame.data);
      let paid = false;
      this.options.handlers.onOutput(bytes, () => {
        if (paid) return;
        paid = true;
        this.owed += bytes.length;
        if (this.owed >= this.window / 4) this.flush();
      });
    } else if (frame.t === "exit") {
      this.flush(); // credit before exit
      this.state = "exited";
      this.options.handlers.onState("exited");
      this.options.handlers.onExit({ code: frame.code, signal: frame.signal, reason: frame.reason });
      this.ended = true;
      this.socket.onopen = this.socket.onmessage = this.socket.onclose = this.socket.onerror = null;
      this.socket.close();
    } else if (frame.t === "error") {
      this.options.handlers.onError(frame.code, frame.message);
    }
  }
}
