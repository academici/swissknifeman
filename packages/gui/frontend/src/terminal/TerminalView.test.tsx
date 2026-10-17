import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeTransport, Wrapper } from "../test/fakes";
import { toBase64, type SocketLike } from "./session";
import { TerminalView } from "./TerminalView";

const mocks = vi.hoisted(() => {
  const terminals: Array<{
    writes: Array<{ data: Uint8Array; callback: () => void }>;
    disposed: number;
    opened: number;
    options: unknown;
    dataHandler: ((data: string) => void) | null;
    cols: number;
    rows: number;
  }> = [];
  const fits = { count: 0, throws: false };
  return { terminals, fits };
});

vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    writes: Array<{ data: Uint8Array; callback: () => void }> = [];
    disposed = 0;
    opened = 0;
    dataHandler: ((data: string) => void) | null = null;
    cols = 100;
    rows = 30;
    constructor(public options: unknown) {
      mocks.terminals.push(this);
    }
    loadAddon() {}
    open() {
      this.opened += 1;
    }
    write(data: Uint8Array, callback: () => void) {
      this.writes.push({ data, callback });
    }
    onData(handler: (data: string) => void) {
      this.dataHandler = handler;
      return { dispose: () => (this.dataHandler = null) };
    }
    onBinary() {
      return { dispose: () => undefined };
    }
    dispose() {
      this.disposed += 1;
    }
  },
}));
vi.mock("@xterm/addon-fit", () => ({
  FitAddon: class {
    fit() {
      mocks.fits.count += 1;
      if (mocks.fits.throws) throw new Error("no size");
    }
    activate() {}
    dispose() {}
  },
}));
vi.mock("@xterm/xterm/css/xterm.css", () => ({}));

class FakeSocket implements SocketLike {
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  sent: Array<Record<string, unknown>> = [];
  closed = 0;
  send(data: string) {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close() {
    this.closed += 1;
  }
}

const observers = { created: 0, observed: 0, disconnected: 0 };

beforeEach(() => {
  mocks.terminals.length = 0;
  mocks.fits.count = 0;
  mocks.fits.throws = false;
  Object.assign(observers, { created: 0, observed: 0, disconnected: 0 });
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        observers.created += 1;
        lastObserver = { callback };
      }
      observe() {
        observers.observed += 1;
      }
      disconnect() {
        observers.disconnected += 1;
      }
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

let lastObserver: { callback: () => void } | null = null;

function mount() {
  const socket = new FakeSocket();
  const fake = new FakeTransport({ "POST /v1/terminal/sessions/term-x:close": { kind: "session" } });
  const exits: unknown[] = [];
  const view = render(
    <Wrapper transport={fake}>
      <TerminalView sessionId="term-x" socketFactory={() => socket} onExit={(info) => exits.push(info)} />
    </Wrapper>,
  );
  return { socket, fake, view, exits };
}

describe("TerminalView", () => {
  it("opens xterm from a dynamic import, sends the first credit and the fitted size", async () => {
    const { socket } = mount();
    expect(screen.getByRole("region", { name: "Terminal" })).toBeTruthy();
    await waitFor(() => expect(mocks.terminals).toHaveLength(1));
    expect(mocks.terminals[0]?.options).toMatchObject({ convertEol: false, cursorBlink: true, scrollback: 5000, allowProposedApi: false });
    expect(mocks.terminals[0]?.opened).toBe(1);
    socket.onopen?.({});
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Connected"));
    expect(socket.sent).toEqual([{ t: "credit", bytes: 16384 }, { t: "resize", cols: 100, rows: 30 }]);
  });

  it("writes output to the terminal and returns the credit only from the write callback", async () => {
    const { socket } = mount();
    await waitFor(() => expect(mocks.terminals).toHaveLength(1));
    socket.onopen?.({});
    socket.sent.length = 0;
    const data = toBase64(new TextEncoder().encode("x".repeat(5000)));
    socket.onmessage?.({ data: JSON.stringify({ t: "output", seq: 0, data }) });
    const term = mocks.terminals[0]!;
    expect(term.writes).toHaveLength(1);
    expect(term.writes[0]?.data.length).toBe(5000);
    expect(socket.sent).toEqual([]); // written? no: the callback has not run, so no credit
    term.writes[0]?.callback();
    expect(socket.sent).toEqual([{ t: "credit", bytes: 5000 }]); // write -> callback -> credit
  });

  it("sends keyboard input and a resize when the container changes", async () => {
    const { socket } = mount();
    await waitFor(() => expect(mocks.terminals).toHaveLength(1));
    socket.onopen?.({});
    socket.sent.length = 0;
    mocks.terminals[0]?.dataHandler?.("ls\r");
    expect(socket.sent).toEqual([{ t: "input", data: toBase64(new TextEncoder().encode("ls\r")) }]);
    mocks.terminals[0]!.cols = 120;
    lastObserver?.callback();
    expect(socket.sent.at(-1)).toEqual({ t: "resize", cols: 120, rows: 30 });
  });

  it("shows the exit code and the reason", async () => {
    const { socket, exits } = mount();
    await waitFor(() => expect(mocks.terminals).toHaveLength(1));
    socket.onopen?.({});
    socket.onmessage?.({ data: JSON.stringify({ t: "exit", code: 7, reason: "exit" }) });
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("exit code 7"));
    expect(screen.getByRole("status").textContent).toContain("Session ended");
    expect(exits).toHaveLength(1);
  });

  it("shows a server error as an alert", async () => {
    const { socket } = mount();
    await waitFor(() => expect(mocks.terminals).toHaveLength(1));
    socket.onmessage?.({ data: JSON.stringify({ t: "error", code: "TERMINAL_BUSY", message: "busy" }) });
    expect((await screen.findByRole("alert")).textContent).toContain("TERMINAL_BUSY");
  });

  it("tears everything down on unmount: socket, observer, terminal and the :close request", async () => {
    const { socket, fake, view } = mount();
    await waitFor(() => expect(mocks.terminals).toHaveLength(1));
    socket.onopen?.({});
    view.unmount();
    expect(socket.closed).toBe(1);
    expect(observers.disconnected).toBe(1);
    expect(mocks.terminals[0]?.disposed).toBe(1);
    expect(mocks.terminals[0]?.dataHandler).toBeNull();
    expect(fake.calls.filter((call) => call.path === "/v1/terminal/sessions/term-x:close" && call.method === "POST")).toHaveLength(1);
  });

  it("creates nothing when it is unmounted before xterm has loaded", async () => {
    const { view, socket } = mount();
    view.unmount();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mocks.terminals).toHaveLength(0);
    expect(socket.closed).toBe(0);
    expect(observers.created).toBe(0);
  });

  it("does not fail when the container has no size yet", async () => {
    mocks.fits.throws = true;
    const { socket } = mount();
    await waitFor(() => expect(mocks.terminals).toHaveLength(1));
    socket.onopen?.({});
    expect(socket.sent).toEqual([{ t: "credit", bytes: 16384 }]);
  });
});
