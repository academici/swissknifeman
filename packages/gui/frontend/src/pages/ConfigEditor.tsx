import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router";
import { ErrorPanel } from "../app/ErrorView";
import { ConflictView } from "../forms/ConflictView";
import { layerOf, layerValues, rebase, type Draft } from "../forms/draft";
import { LayerPicker } from "../forms/LayerPicker";
import { PreviewDialog } from "../forms/PreviewDialog";
import { formatValue, ProvenanceBadge } from "../forms/ProvenanceBadge";
import { SchemaForm } from "../forms/SchemaForm";
import type { ConfigView, LayerName, Value } from "../forms/types";
import { useTransport } from "../transport/context";
import { useProjects } from "./Projects";

const MODES = ["form", "diff", "raw", "explain"] as const;
type Mode = (typeof MODES)[number];

const viewPath = (module: string, projectId: string | null) =>
  `/v1/config/${encodeURIComponent(module)}/effective${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`;

function DiffMode({ draft }: { draft: Draft | null }) {
  if (!draft || draft.ops.size === 0) return <div className="muted">No changes.</div>;
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Key</th>
          <th>In the file</th>
          <th>Draft</th>
        </tr>
      </thead>
      <tbody>
        {[...draft.ops].map(([key, op]) => (
          <tr key={key}>
            <td>{key}</td>
            <td>{formatValue(draft.base[key])}</td>
            <td>{op.op === "set" ? formatValue(op.value) : <em>unset</em>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RawMode({ view, layer }: { view: ConfigView; layer: LayerName }) {
  const record = layerOf(view, layer);
  if (!record) return <div className="muted">No such layer.</div>;
  return (
    <div>
      <div className="muted">{record.file ?? "no file"}{record.revision ? ` · ${record.revision}` : ""}</div>
      {record.raw === null ? <div className="muted">{record.raw_truncated ? "The file is too large to show." : "Not available."}</div> : <pre data-testid="raw">{record.raw}</pre>}
    </div>
  );
}

function ExplainMode({ view }: { view: ConfigView }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Key</th>
          <th>Effective and what it overrides</th>
        </tr>
      </thead>
      <tbody>
        {view.entries.map((entry) => (
          <tr key={entry.key}>
            <td>{entry.key}</td>
            <td>
              <ProvenanceBadge entry={entry} open />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

type Dialog = { kind: "none" } | { kind: "preview" } | { kind: "conflict"; fresh: ConfigView };

function Editor({ view, layer, projectId }: { view: ConfigView; layer: LayerName; projectId: string | null }) {
  const transport = useTransport();
  const queryClient = useQueryClient();
  const [search, setSearch] = useSearchParams();
  const mode: Mode = MODES.find((candidate) => candidate === search.get("mode")) ?? "form";
  const [draft, setDraft] = useState<Draft | null>(null);
  const [dialog, setDialog] = useState<Dialog>({ kind: "none" });
  const [error, setError] = useState<unknown>(null);
  const count = draft?.ops.size ?? 0;

  function setMode(next: Mode) {
    const params = new URLSearchParams(search);
    params.set("mode", next);
    setSearch(params, { replace: true });
  }

  async function conflict() {
    try {
      const fresh = await queryClient.fetchQuery({ queryKey: ["config", view.module, projectId], staleTime: 0,
        queryFn: () => transport.request<ConfigView>("GET", viewPath(view.module, projectId)) });
      setDialog({ kind: "conflict", fresh });
    } catch (caught) {
      setDialog({ kind: "none" });
      setError(caught);
    }
  }

  function applied() {
    setDraft(null);
    setDialog({ kind: "none" });
    void queryClient.invalidateQueries({ queryKey: ["config", view.module] });
  }

  function reapply(fresh: ConfigView) {
    const next = draft ? rebase(draft, fresh) : null;
    setDraft(next && next.ops.size > 0 ? next : null);
    setDialog(next && next.ops.size > 0 ? { kind: "preview" } : { kind: "none" });
  }

  return (
    <div>
      {view.warnings.length > 0 && (
        <ul className="muted">
          {view.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      <div className="tabs" role="tablist">
        {MODES.map((candidate) => (
          <button key={candidate} type="button" role="tab" aria-selected={candidate === mode} disabled={candidate === mode}
                  onClick={() => setMode(candidate)}>
            {candidate[0]?.toUpperCase()}
            {candidate.slice(1)}
          </button>
        ))}
      </div>
      {error ? <ErrorPanel error={error} /> : null}
      {mode === "form" && <SchemaForm view={view} layer={layer} draft={draft} onDraft={setDraft} />}
      {mode === "diff" && <DiffMode draft={draft} />}
      {mode === "raw" && <RawMode view={view} layer={layer} />}
      {mode === "explain" && <ExplainMode view={view} />}
      <div className="buttons config-actions">
        <button type="button" disabled={count === 0 || dialog.kind !== "none"} onClick={() => setDialog({ kind: "preview" })}>
          Preview ({count})
        </button>
        <button type="button" disabled={count === 0} onClick={() => setDraft(null)}>
          Discard changes
        </button>
      </div>
      {dialog.kind === "preview" && draft && (
        <PreviewDialog draft={draft} projectId={projectId} onApplied={applied} onConflict={() => void conflict()}
                       onClose={() => setDialog({ kind: "none" })} />
      )}
      {dialog.kind === "conflict" && draft && (
        <ConflictView draft={draft} current={layerValues(dialog.fresh, layer) as Record<string, Value | null>}
                      onReload={() => { setDraft(null); setDialog({ kind: "none" }); }}
                      onReapply={() => reapply(dialog.fresh)} />
      )}
    </div>
  );
}

/** `/settings/config/:module?layer=&project=&mode=`: the configuration of one module, editable in two layers. */
export function ConfigEditor() {
  const { module = "" } = useParams();
  const transport = useTransport();
  const [search, setSearch] = useSearchParams();
  const projects = useProjects();
  const projectId = search.get("project");
  const wanted: LayerName = search.get("layer") === "project" ? "project" : "machine";
  const layer: LayerName = wanted === "project" && projectId ? "project" : "machine";
  const view = useQuery({
    queryKey: ["config", module, projectId],
    queryFn: () => transport.request<ConfigView>("GET", viewPath(module, projectId)),
    refetchOnWindowFocus: true,
  });

  function update(changes: Record<string, string | null>) {
    const params = new URLSearchParams(search);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) params.delete(key);
      else params.set(key, value);
    }
    setSearch(params);
  }

  return (
    <div>
      <h1>Configuration: {module}</h1>
      <LayerPicker layer={layer} projectId={projectId} projects={projects.data?.projects ?? []}
                   onLayer={(next) => update({ layer: next })}
                   onProject={(next) => update(next ? { project: next } : { project: null, layer: "machine" })} />
      {view.isPending && <div className="muted">Loading…</div>}
      {view.isError && <ErrorPanel error={view.error} />}
      {view.data && <Editor key={`${module}|${layer}|${projectId ?? ""}`} view={view.data} layer={layer} projectId={projectId} />}
    </div>
  );
}
