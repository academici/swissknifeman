import { Link } from "react-router";
import { ErrorPanel } from "../app/ErrorView";
import { Flag, StateBadge } from "../plugins/Badges";
import { usePlugins, type PluginDoc } from "../plugins/api";

function compatibility(plugin: PluginDoc): string {
  const { protocol_ok: ok, missing_contracts: missing } = plugin.compatibility;
  const parts = [ok ? "protocol ok" : "protocol mismatch"];
  if (missing.length > 0) parts.push(`missing ${missing.map((entry) => `${entry.id.split(":").pop() ?? entry.id} ${entry.version}`).join(", ")}`);
  return parts.join("; ");
}

/** `/plugins`: every plugin with its state (text and badge), flags, compatibility, failures and grants. */
export function Plugins() {
  const plugins = usePlugins();
  return (
    <div>
      <h1>Plugins</h1>
      {plugins.isError && <ErrorPanel error={plugins.error} />}
      {plugins.isPending && <div className="muted">Loading the plugins…</div>}
      {plugins.data && (
        <table className="table plugin-list">
          <thead>
            <tr>
              <th>Plugin</th>
              <th>Source</th>
              <th>State</th>
              <th>Flags</th>
              <th>Compatibility</th>
              <th>Failures</th>
              <th>Grants</th>
            </tr>
          </thead>
          <tbody>
            {plugins.data.plugins.map((plugin) => (
              <tr key={plugin.id}>
                <td>
                  <Link to={`/plugins/${encodeURIComponent(plugin.id)}`}>{plugin.id}</Link>
                </td>
                <td>{plugin.source}</td>
                <td>
                  <StateBadge state={plugin.state} />
                </td>
                <td>
                  <Flag label="runtime" on={plugin.runtime_enabled} /> <Flag label="ui" on={plugin.ui_enabled} />
                </td>
                <td>{compatibility(plugin)}</td>
                <td>
                  {plugin.failures.count} in {plugin.failures.window_s} s{plugin.failures.last_code ? `, last ${plugin.failures.last_code}` : ""}
                </td>
                <td>{plugin.grants.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {plugins.data && plugins.data.plugins.length === 0 && <div className="muted">No plugins.</div>}
    </div>
  );
}
