import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import type { Run, RunList } from "../contracts";
import { ErrorPanel } from "../app/ErrorView";
import { useCommands } from "../components/CommandRunner";
import { RunLog } from "../components/RunLog";
import { useTransport } from "../transport/context";
import { StatusBadge } from "../views/common";

const ENDED = new Set(["denied", "failed_to_start", "succeeded", "failed", "cancelled", "timed_out", "lost"]);

export function Runs() {
  const transport = useTransport();
  const queryClient = useQueryClient();
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => transport.request<RunList>("GET", "/v1/runs?limit=100") });
  useEffect(() => {
    const subscription = transport.subscribe(
      { types: ["gui.run"] },
      {
        onFrame: () => void queryClient.invalidateQueries({ queryKey: ["runs"] }),
        onSnapshotRequired: () => void queryClient.invalidateQueries({ queryKey: ["runs"] }),
      },
    );
    return () => subscription.close();
  }, [queryClient, transport]);
  return (
    <div>
      <h1>Runs</h1>
      {runs.isError && <ErrorPanel error={runs.error} />}
      <table className="resource-list">
        <thead>
          <tr>
            <th>Run</th>
            <th>Command</th>
            <th>State</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {runs.data?.runs.map((run) => (
            <tr key={run.run_id}>
              <td>
                <Link to={`/runs/${run.run_id}`}>{run.run_id.slice(0, 12)}…</Link>
              </td>
              <td>
                {run.command}
                {run.dry_run ? " (dry run)" : ""}
              </td>
              <td>
                <StatusBadge status={run.state} />
              </td>
              <td>{run.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RunPage() {
  const { runId = "" } = useParams();
  const transport = useTransport();
  const commands = useCommands();
  const [cancelError, setCancelError] = useState<unknown>(null);
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => transport.request<Run>("GET", `/v1/runs/${encodeURIComponent(runId)}`),
  });
  if (run.isPending) return <div className="muted">Loading the run…</div>;
  if (run.isError) return <ErrorPanel error={run.error} />;
  const doc = run.data;
  const command = commands.data?.commands.find((entry) => entry.id === doc.command);
  const cancellable = doc.state === "running" && Boolean(command?.supports?.includes("cancel"));

  async function cancel() {
    setCancelError(null);
    try {
      await transport.request<Run>("POST", `/v1/runs/${encodeURIComponent(runId)}:cancel`, {});
      void run.refetch();
    } catch (caught) {
      setCancelError(caught);
    }
  }

  return (
    <div>
      <h1>
        {command?.title ?? doc.command} <StatusBadge status={doc.state} />
      </h1>
      <dl className="run-facts">
        <dt>Run</dt>
        <dd>{doc.run_id}</dd>
        <dt>Owner</dt>
        <dd>{doc.owner}</dd>
        <dt>Dry run</dt>
        <dd>{doc.dry_run ? "yes" : "no"}</dd>
        <dt>Decision</dt>
        <dd>{doc.permission.decision}</dd>
        {doc.exit && (
          <>
            <dt>Exit</dt>
            <dd>{doc.exit.signal ?? doc.exit.code}</dd>
          </>
        )}
      </dl>
      {doc.error && <ErrorPanel error={new Error(`${doc.error.code}: ${doc.error.message}`)} title="The run did not succeed" />}
      {cancellable && (
        <button type="button" onClick={() => void cancel()}>
          Cancel
        </button>
      )}
      {cancelError ? <ErrorPanel error={cancelError} /> : null}
      {!ENDED.has(doc.state) && <div className="muted">Live…</div>}
      <RunLog runId={doc.run_id} />
    </div>
  );
}
