import { useEffect, useRef, useState } from "react";
import type { ITerminalAddon, Terminal as XTerminal } from "@xterm/xterm";
import { useTransport } from "../transport/context";
import { TerminalSession, type EndReason, type SessionState, type SocketLike } from "./session";

export interface TerminalExit {
  code: number;
  signal?: number;
  reason: EndReason;
}

interface Props {
  sessionId: string;
  cols?: number;
  rows?: number;
  /** Tests give a fake socket; the default is a WebSocket on the origin of the page. */
  socketFactory?: (url: string) => SocketLike;
  onExit?: (info: TerminalExit) => void;
  /** Called after the terminal and the session were torn down and the `:close` was sent. */
  onClosed?: () => void;
}

interface FitLike extends ITerminalAddon {
  fit(): void;
}

const STATE_TEXT: Record<SessionState | "loading", string> = {
  loading: "Loading the terminal…",
  connecting: "Connecting…",
  open: "Connected",
  exited: "Session ended",
  closed: "Connection closed",
  failed: "Connection failed",
};

/**
 * The terminal of one session. xterm.js and its fit addon are imported dynamically (a chunk of their own, not part of
 * the initial bundle). Output goes only through `term.write`; there is no HTML path, no clipboard addon and no link
 * addon. The credit goes back to the server from the write callback.
 */
export function TerminalView({ sessionId, cols = 80, rows = 24, socketFactory, onExit, onClosed }: Props) {
  const transport = useTransport();
  const host = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<SessionState | "loading">("loading");
  const [exit, setExit] = useState<TerminalExit | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const callbacks = useRef({ onExit, onClosed });
  useEffect(() => {
    callbacks.current = { onExit, onClosed };
  });

  useEffect(() => {
    let cancelled = false;
    let teardown: (() => void) | null = null;
    let refused = false; // the server refused the attachment: the session belongs to another client

    const closeRemote = () => {
      if (refused) return;
      void transport.request("POST", `/v1/terminal/sessions/${encodeURIComponent(sessionId)}:close`, {}).catch(() => undefined).finally(() => callbacks.current.onClosed?.());
    };

    void (async () => {
      const [xterm, fit] = await Promise.all([import("@xterm/xterm"), import("@xterm/addon-fit"), import("@xterm/xterm/css/xterm.css")]);
      const element = host.current;
      if (cancelled || !element) {
        if (cancelled) closeRemote(); // the backend session exists already; nothing else was created
        return;
      }
      const term: XTerminal = new xterm.Terminal({ convertEol: false, cursorBlink: true, scrollback: 5000, allowProposedApi: false, cols, rows });
      const fitAddon = new fit.FitAddon() as FitLike;
      term.loadAddon(fitAddon);
      term.open(element);

      const session = new TerminalSession({
        sessionId,
        socketFactory,
        handlers: {
          onOutput: (bytes, written) => term.write(bytes, written),
          onExit: (info) => {
            setExit(info);
            callbacks.current.onExit?.(info);
          },
          onError: (code, message) => {
            if (code === "TERMINAL_BUSY" || code === "NOT_FOUND") refused = true;
            setProblem(`${code}: ${message}`);
          },
          onState: (next) => {
            setState(next);
            if (next === "open") refit();
          },
        },
      });

      function refit() {
        try {
          fitAddon.fit();
        } catch {
          return; // the container has no size yet
        }
        const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, Math.round(value)));
        session.sendResize(clamp(term.cols, 10, 500), clamp(term.rows, 2, 200));
      }

      const input = term.onData((data) => session.sendInput(data));
      const binary = term.onBinary((data) => session.sendInput(Uint8Array.from(data, (char) => char.charCodeAt(0))));
      const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => refit());
      observer?.observe(element);

      teardown = () => {
        observer?.disconnect();
        input.dispose();
        binary.dispose();
        session.close();
        term.dispose();
        closeRemote();
      };
    })();

    return () => {
      cancelled = true;
      teardown?.();
      teardown = null;
    };
    // the session is opened once per id; size props only seed the first fit
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, transport]);

  return (
    <div className="terminal-view">
      <div className="terminal-status" role="status">
        {STATE_TEXT[state]}
        {exit && ` — exit code ${exit.code}${exit.signal ? `, signal ${exit.signal}` : ""} (${exit.reason})`}
      </div>
      {problem && (
        <div className="error-panel" role="alert">
          {problem}
        </div>
      )}
      <div className="terminal-host" ref={host} role="region" aria-label="Terminal" />
    </div>
  );
}
