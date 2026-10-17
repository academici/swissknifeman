import { describe, expect, it } from "vitest";
import { CREDIT_WINDOW, TerminalSession, fromBase64, terminalUrl, toBase64, type SessionHandlers, type SocketLike } from "./session";

class FakeSocket implements SocketLike {
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  sent: Array<Record<string, unknown>> = [];
  closed = 0;
  constructor(public url: string) {}
  send(data: string) {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close() {
    this.closed += 1;
  }
  serve(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

function setup() {
  const log: string[] = [];
  const writes: Array<{ bytes: Uint8Array; written: () => void }> = [];
  const exits: unknown[] = [];
  let socket!: FakeSocket;
  const handlers: SessionHandlers = {
    onOutput: (bytes, written) => {
      log.push("write");
      writes.push({ bytes, written });
    },
    onExit: (info) => exits.push(info),
    onError: (code) => log.push(`error ${code}`),
    onState: (state) => log.push(`state ${state}`),
  };
  const session = new TerminalSession({
    sessionId: "term-" + "a".repeat(32),
    handlers,
    location: { protocol: "http:", host: "127.0.0.1:8765" },
    socketFactory: (url) => (socket = new FakeSocket(url)),
  });
  return { session, socket, log, writes, exits };
}

const out = (seq: number, text: string) => ({ t: "output", seq, data: toBase64(new TextEncoder().encode(text)) });

describe("terminal session", () => {
  it("opens the socket of the session on the same origin and sends the first credit at once", () => {
    const { socket, session } = setup();
    expect(socket.url).toBe(`ws://127.0.0.1:8765/v1/terminal/term-${"a".repeat(32)}/io`);
    expect(terminalUrl("term-x", { protocol: "https:", host: "h" })).toBe("wss://h/v1/terminal/term-x/io");
    expect(socket.sent).toEqual([]);
    socket.onopen?.({});
    expect(session.state).toBe("open");
    expect(socket.sent).toEqual([{ t: "credit", bytes: CREDIT_WINDOW }]);
  });

  it("returns credit only after the write callback, in batches of at least a quarter of the window", () => {
    const { socket, writes, log } = setup();
    socket.onopen?.({});
    socket.sent.length = 0;
    socket.serve(out(0, "x".repeat(1000)));
    expect(log).toContain("write");
    expect(socket.sent).toEqual([]); // written to the terminal? not yet: no credit before the callback
    writes[0]?.written();
    expect(socket.sent).toEqual([]); // 1000 < window/4: kept for the batch
    socket.serve(out(1, "y".repeat(3200)));
    writes[1]?.written();
    expect(socket.sent).toEqual([{ t: "credit", bytes: 4200 }]);
    writes[1]?.written(); // a callback twice pays once
    expect(socket.sent).toHaveLength(1);
  });

  it("pays the owed credit before the exit and stops", () => {
    const { socket, writes, exits, session } = setup();
    socket.onopen?.({});
    socket.sent.length = 0;
    socket.serve(out(0, "bye"));
    writes[0]?.written();
    socket.serve({ t: "exit", code: 3, reason: "exit" });
    expect(socket.sent).toEqual([{ t: "credit", bytes: 3 }]);
    expect(exits).toEqual([{ code: 3, signal: undefined, reason: "exit" }]);
    expect(session.state).toBe("exited");
    expect(socket.closed).toBe(1);
  });

  it("encodes input as base64 bytes (UTF-8) and cuts large input", () => {
    const { socket, session } = setup();
    session.sendInput("ls\r"); // before open: dropped
    expect(socket.sent).toEqual([]);
    socket.onopen?.({});
    socket.sent.length = 0;
    session.sendInput("é\r");
    expect(socket.sent).toEqual([{ t: "input", data: "w6kN" }]);
    expect(Array.from(fromBase64("w6kN"))).toEqual([0xc3, 0xa9, 0x0d]);
    socket.sent.length = 0;
    session.sendInput(new Uint8Array(70 * 1024));
    expect(socket.sent).toHaveLength(3);
    expect(socket.sent.every((frame) => frame.t === "input")).toBe(true);
  });

  it("sends a resize once per size", () => {
    const { socket, session } = setup();
    socket.onopen?.({});
    socket.sent.length = 0;
    session.sendResize(100, 30);
    session.sendResize(100, 30);
    session.sendResize(120, 40);
    expect(socket.sent).toEqual([
      { t: "resize", cols: 100, rows: 30 },
      { t: "resize", cols: 120, rows: 40 },
    ]);
  });

  it("reports server errors, ignores junk frames and reports a lost socket", () => {
    const { socket, session, log } = setup();
    socket.onopen?.({});
    socket.serve({ t: "error", code: "TERMINAL_BUSY", message: "busy" });
    socket.onmessage?.({ data: "not json" });
    socket.onmessage?.({ data: new ArrayBuffer(2) });
    expect(log).toContain("error TERMINAL_BUSY");
    socket.onclose?.({});
    expect(session.state).toBe("closed");
  });

  it("close() closes the socket once and ignores later frames", () => {
    const { socket, session, writes } = setup();
    socket.onopen?.({});
    session.close();
    session.close();
    expect(socket.closed).toBe(1);
    expect(session.state).toBe("closed");
    expect(socket.onmessage).toBeNull();
    expect(writes).toHaveLength(0);
  });
});
