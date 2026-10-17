import { useCallback, useEffect, useState, type ReactNode } from "react";
import { tauriGlobal, type TauriGlobal } from "../transport/TauriTransport";

export type SidecarState = "starting" | "ready" | "restarting" | "failed";

export interface SidecarStatus {
  state: SidecarState;
  port?: number;
  restarts: number;
  last_error?: string;
}

const POLL_MS = 2000;
const LOG_LINES = 200;
const STATES: SidecarState[] = ["starting", "ready", "restarting", "failed"];

function readStatus(value: unknown): SidecarStatus | null {
  const item = value as Partial<SidecarStatus> | null;
  if (!item || typeof item !== "object" || !STATES.includes(item.state as SidecarState)) return null;
  return {
    state: item.state as SidecarState,
    restarts: typeof item.restarts === "number" ? item.restarts : 0,
    last_error: typeof item.last_error === "string" ? item.last_error : undefined,
  };
}

interface Polled {
  status: SidecarStatus | null;
  log: string[];
  unreadable: boolean;
  restart(): void;
}

/** Polls `sidecar_status` and `sidecar_log` every 2 s (no events); the timer dies with the component. */
export function useSidecar(tauri: TauriGlobal | undefined, pollMs: number = POLL_MS): Polled {
  const [status, setStatus] = useState<SidecarStatus | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [unreadable, setUnreadable] = useState(false);

  const poll = useCallback(async () => {
    if (!tauri) return;
    try {
      const next = readStatus(await tauri.core.invoke("sidecar_status"));
      const lines = await tauri.core.invoke("sidecar_log", { lines: LOG_LINES });
      setStatus(next);
      setUnreadable(next === null);
      setLog(Array.isArray(lines) ? lines.filter((line): line is string => typeof line === "string").slice(-LOG_LINES) : []);
    } catch {
      setUnreadable(true);
    }
  }, [tauri]);

  useEffect(() => {
    let alive = true;
    const run = () => {
      if (alive) void poll();
    };
    run();
    const timer = setInterval(run, pollMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [poll, pollMs]);

  const restart = useCallback(() => {
    if (!tauri) return;
    void tauri.core.invoke("sidecar_restart").then(poll, () => setUnreadable(true));
  }, [tauri, poll]);

  return { status, log, unreadable, restart };
}

export function DiagnosticsView({ polled, children }: { polled: Polled; children?: ReactNode }) {
  const { status, log, unreadable, restart } = polled;
  return (
    <div className="diagnostics" role="region" aria-label="Sidecar diagnostics">
      <h2>SKM backend (sidecar)</h2>
      {status ? (
        <dl className="diagnostics-facts">
          <dt>State</dt>
          <dd>
            <span className={`state state-${status.state}`} data-testid="sidecar-state">{status.state}</span>
          </dd>
          <dt>Restarts</dt>
          <dd data-testid="sidecar-restarts">{status.restarts}</dd>
          <dt>Last error</dt>
          <dd data-testid="sidecar-error">{status.last_error ?? "none"}</dd>
        </dl>
      ) : (
        <div className="muted">{unreadable ? "The sidecar state cannot be read" : "Reading the sidecar state…"}</div>
      )}
      {status && unreadable && <div className="muted">The last refresh failed</div>}
      {children}
      <div>
        <button type="button" onClick={restart}>Restart sidecar</button>
      </div>
      <h3>Log (last {LOG_LINES} lines)</h3>
      <pre className="diagnostics-log" data-testid="sidecar-log">{log.length > 0 ? log.join("\n") : "(empty)"}</pre>
    </div>
  );
}

/** Standalone screen (used by the handshake when the backend does not fit). */
export function Diagnostics({ tauri, pollMs, children }: { tauri?: TauriGlobal; pollMs?: number; children?: ReactNode }) {
  const polled = useSidecar(tauri ?? tauriGlobal(), pollMs);
  return <DiagnosticsView polled={polled}>{children}</DiagnosticsView>;
}

/** The application opens only while the sidecar is `ready`; otherwise the diagnostics screen takes its place. */
export function SidecarGate({ tauri, pollMs, children }: { tauri?: TauriGlobal; pollMs?: number; children: ReactNode }) {
  const polled = useSidecar(tauri ?? tauriGlobal(), pollMs);
  if (polled.status?.state === "ready") return <>{children}</>;
  return <DiagnosticsView polled={polled} />;
}
