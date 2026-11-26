import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { Bootstrap } from "../contracts";
import type { Session, SessionList, SessionRequest } from "../contracts/generated/terminal";
import { ErrorPanel } from "../app/ErrorView";
import { ConfirmDialog } from "../plugins/GrantDialog";
import { useConfirmed } from "../plugins/useConfirmed";
import { TerminalView } from "../terminal/TerminalView";
import { useTransport } from "../transport/context";
import { useProjects } from "./Projects";

const CONTRACT = "urn:swissknifeman:gui:terminal:v1";
const SESSIONS = "/v1/terminal/sessions";
const FEATURE = "terminal";

/** Whether the backend announced the terminal (`bootstrap.features`); the handshake is cached by the gate. */
export function useTerminalFeature(): { known: boolean; enabled: boolean } {
  const transport = useTransport();
  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () => transport.request<Bootstrap>("GET", "/v1/bootstrap"),
    staleTime: Infinity,
  });
  return { known: bootstrap.data !== undefined, enabled: bootstrap.data?.features.includes(FEATURE) ?? false };
}

/** `/terminal`: a shell in a trusted project, started after the operator confirms the summary of the backend. */
export function Terminal() {
  const feature = useTerminalFeature();
  if (!feature.known) return <div className="muted">Loading…</div>;
  if (!feature.enabled) {
    return (
      <div>
        <h1>Terminal</h1>
        <div className="muted" role="status">
          Terminal is disabled. The owner turns it on with <code>[gui.terminal] enabled = true</code> in the machine
          configuration (browser mode only).
        </div>
      </div>
    );
  }
  return <TerminalPage />;
}

function TerminalPage() {
  const transport = useTransport();
  const queryClient = useQueryClient();
  const projects = useProjects();
  const sessions = useQuery({ queryKey: ["terminal-sessions"], queryFn: () => transport.request<SessionList>("GET", SESSIONS) });
  const confirmed = useConfirmed();
  const [project, setProject] = useState("");
  const [active, setActive] = useState<Session | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["terminal-sessions"] });
  const projectId = project || projects.data?.projects[0]?.id || "";

  const close = useMutation({
    mutationFn: (id: string) => transport.request<Session>("POST", `${SESSIONS}/${encodeURIComponent(id)}:close`, {}),
    onSettled: () => refresh(),
  });

  function open(event: FormEvent) {
    event.preventDefault();
    if (!projectId) return;
    // the body is made once: the confirmation is bound to project and size
    const body: SessionRequest = { $schema: CONTRACT, kind: "session_request", project_id: projectId, cols: 80, rows: 24 };
    void confirmed.run("Open terminal", async (confirm) => {
      const session = await transport.request<Session>("POST", SESSIONS, confirm ? { ...body, confirm } : body);
      setActive(session);
      void refresh();
    });
  }

  return (
    <div>
      <h1>Terminal</h1>
      {!active && (
        <form className="add-project" onSubmit={open}>
          <label>
            Project{" "}
            <select value={projectId} onChange={(event) => setProject(event.target.value)} aria-label="Project">
              {(projects.data?.projects ?? []).map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={!projectId || confirmed.busy}>
            Open terminal
          </button>
        </form>
      )}
      {projects.isError && <ErrorPanel error={projects.error} />}
      {confirmed.error != null && <ErrorPanel error={confirmed.error} title="The terminal did not start" />}
      {confirmed.pending && (
        <ConfirmDialog pending={confirmed.pending} busy={confirmed.busy} action="Confirm" onCancel={confirmed.cancel} />
      )}
      {active && (
        <div>
          <p className="muted">
            Session {active.session_id} in project {active.project_id}, shell {active.shell}
          </p>
          <button type="button" onClick={() => setActive(null)}>
            Close
          </button>
          <TerminalView sessionId={active.session_id} cols={active.cols} rows={active.rows} onClosed={() => void refresh()} />
        </div>
      )}
      <h2>Active sessions</h2>
      {sessions.isError && <ErrorPanel error={sessions.error} />}
      {sessions.data && sessions.data.sessions.length === 0 && <div className="muted">No active session.</div>}
      <ul className="terminal-sessions">
        {(sessions.data?.sessions ?? []).map((entry) => (
          <li key={entry.session_id}>
            <code>{entry.session_id}</code> · {entry.project_id} · {entry.shell} · {entry.cols}×{entry.rows}{" "}
            {active?.session_id !== entry.session_id && (
              <>
                <button type="button" onClick={() => setActive({ $schema: CONTRACT, kind: "session", ...entry })}>
                  Attach
                </button>{" "}
                <button type="button" disabled={close.isPending} onClick={() => close.mutate(entry.session_id)}>
                  Close session
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
      {close.isError && <ErrorPanel error={close.error} />}
    </div>
  );
}
