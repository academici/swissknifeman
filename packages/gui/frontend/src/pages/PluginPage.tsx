import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import type { ActionResult } from "../contracts/generated/plugin-api";
import { ErrorPanel } from "../app/ErrorView";
import { EnforcementBadge, Flag, StateBadge } from "../plugins/Badges";
import { ConfirmDialog, GrantDialog } from "../plugins/GrantDialog";
import { actionBody, invalidatePlugins, paths, usePlugin, usePluginHistory, type PluginDoc } from "../plugins/api";
import { useConfirmed } from "../plugins/useConfirmed";
import { ApiError } from "../transport/ApiError";
import { useTransport } from "../transport/context";
import { useProjects } from "./Projects";

const CAN_ENABLE = new Set(["compatible", "disabled"]);

function Permissions({ plugin }: { plugin: PluginDoc }) {
  return (
    <section aria-label="Permissions">
      <h2>Permissions</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Effect</th>
            <th>Declared</th>
            <th>Enforcement</th>
            <th>Start</th>
          </tr>
        </thead>
        <tbody>
          {plugin.permissions.map((entry) => (
            <tr key={entry.effect}>
              <td>{entry.effect}</td>
              <td>{entry.declared ? "yes" : "no"}</td>
              <td>
                <EnforcementBadge value={entry.enforcement} />
              </td>
              <td>{plugin.source === "extension" && entry.declared && entry.effect !== "read" ? "start requires a grant" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">There is no sandbox yet: a grant decides whether work may start, it does not limit a running process.</p>
    </section>
  );
}

export function PluginPage() {
  const { pluginId = "" } = useParams();
  const transport = useTransport();
  const queryClient = useQueryClient();
  const projects = useProjects();
  const [projectId, setProjectId] = useState("");
  const plugin = usePlugin(pluginId, projectId || null);
  const history = usePluginHistory(pluginId);
  const [granting, setGranting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const confirmed = useConfirmed();

  if (plugin.isPending) return <div className="muted">Loading the plugin…</div>;
  if (plugin.isError) return <ErrorPanel error={plugin.error} />;
  const doc = plugin.data;

  function act(verb: "enable" | "disable" | "release") {
    setNotice(null);
    void confirmed.run(`${verb[0]?.toUpperCase()}${verb.slice(1)} ${doc.id}`, async (confirm) => {
      const result = await transport.request<ActionResult>("POST", paths.action(doc.id, verb), actionBody(confirm));
      invalidatePlugins(queryClient);
      if (verb === "disable") setNotice(`Disabled: ${result.drained} run(s) finished, ${result.cancelled} cancelled.`);
    });
  }

  function revoke(grantId: string) {
    setNotice(null);
    void confirmed.run(`Revoke a grant of ${doc.id}`, async (confirm) => {
      await transport.request<ActionResult>("POST", paths.revoke(doc.id, grantId), actionBody(confirm));
      invalidatePlugins(queryClient);
    });
  }

  const findings = confirmed.error instanceof ApiError && confirmed.error.code === "PLUGIN_CONFORMANCE_FAILED"
    ? String(confirmed.error.details.findings ?? "") : "";

  return (
    <div className="plugin-page">
      <p>
        <Link to="/plugins">Plugins</Link>
      </p>
      <h1>
        {doc.id} <StateBadge state={doc.state} />
      </h1>
      <div className="buttons">
        {CAN_ENABLE.has(doc.state) && (
          <button type="button" aria-label={`Enable ${doc.id}`} disabled={confirmed.busy} onClick={() => act("enable")}>
            Enable
          </button>
        )}
        {doc.runtime_enabled && (
          <button type="button" aria-label={`Disable ${doc.id}`} disabled={confirmed.busy} onClick={() => act("disable")}>
            Disable
          </button>
        )}
        <Flag label="runtime" on={doc.runtime_enabled} /> <Flag label="ui" on={doc.ui_enabled} />
        <span className="muted">{doc.source}</span>
      </div>
      {notice && <div role="status">{notice}</div>}
      {confirmed.error ? <ErrorPanel error={confirmed.error} /> : null}
      {findings && <pre className="findings">{findings}</pre>}
      {confirmed.pending && (
        <ConfirmDialog pending={confirmed.pending} busy={confirmed.busy} action="Confirm" onCancel={confirmed.cancel} />
      )}

      <section aria-label="Health">
        <h2>Health</h2>
        <dl className="run-facts">
          <dt>State</dt>
          <dd>{doc.state.replace(/_/g, " ")}</dd>
          <dt>Failures</dt>
          <dd>
            {doc.failures.count} in {doc.failures.window_s} s{doc.failures.last_code ? `, last ${doc.failures.last_code}` : ""}
          </dd>
          <dt>Compatibility</dt>
          <dd>
            {doc.compatibility.protocol_ok ? "protocol ok" : "protocol mismatch"}
            {doc.compatibility.missing_contracts.length > 0 && `; missing ${doc.compatibility.missing_contracts.map((entry) => `${entry.id} ${entry.version}`).join(", ")}`}
          </dd>
          <dt>Manifest</dt>
          <dd>
            <code>{doc.manifest_digest}</code>
          </dd>
        </dl>
        {doc.state === "quarantined" && (
          <div className="cfg-notice" role="status">
            This plugin is in quarantine after repeated failures; nothing of it runs until it is released.{" "}
            <button type="button" aria-label={`Release ${doc.id}`} disabled={confirmed.busy} onClick={() => act("release")}>
              Release
            </button>
          </div>
        )}
        {doc.state === "permission_denied" && (
          <div className="cfg-notice" role="status">
            The manifest now declares more effects: the old grants were voided. Grant again to run its commands.
          </div>
        )}
      </section>

      <Permissions plugin={doc} />

      <section aria-label="Grants">
        <h2>Grants</h2>
        <label>
          Project{" "}
          <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
            <option value="">all projects only</option>
            {projects.data?.projects.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
        {doc.grants.length === 0 ? (
          <div className="muted">No grants.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Effect</th>
                <th>Project</th>
                <th>Expires</th>
                <th>Manifest</th>
                <th>By</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {doc.grants.map((grant) => (
                <tr key={grant.id}>
                  <td>{grant.capability}</td>
                  <td>{grant.project_id ?? "all projects"}</td>
                  <td>{grant.expires_at ?? "never"}</td>
                  <td>
                    <code>{grant.manifest_digest.slice(0, 19)}…</code>
                  </td>
                  <td>{grant.granted_by}</td>
                  <td>
                    <button type="button" aria-label={`Revoke ${grant.capability} grant of ${doc.id}`} disabled={confirmed.busy} onClick={() => revoke(grant.id)}>
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {doc.source === "extension" && !granting && (
          <button type="button" aria-label={`Grant for ${doc.id}`} onClick={() => setGranting(true)}>
            Grant…
          </button>
        )}
        {granting && <GrantDialog plugin={doc} projectId={projectId || null} onClose={() => setGranting(false)} />}
      </section>

      <section aria-label="History">
        <h2>History</h2>
        {history.isError && <ErrorPanel error={history.error} />}
        {history.data && history.data.entries.length === 0 && <div className="muted">No history.</div>}
        {history.data && history.data.entries.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Kind</th>
                <th>Code</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {history.data.entries.map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.at}</td>
                  <td>{entry.kind}</td>
                  <td>{entry.code ?? ""}</td>
                  <td>{entry.detail ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
