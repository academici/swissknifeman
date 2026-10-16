import { useEffect, useState } from "react";
import { ErrorPanel } from "../app/ErrorView";
import { ApiError } from "../transport/ApiError";
import { useTransport } from "../transport/context";
import { previewRequest, type Draft } from "./draft";
import { formatValue } from "./ProvenanceBadge";
import { MUTATION_CONTRACT, type CommitRequest, type CommitResult, type Preview, type Value } from "./types";

const query = (projectId: string | null) => (projectId ? `?project_id=${encodeURIComponent(projectId)}` : "");

const shown = (value: unknown) => formatValue(value as Value | null);

/**
 * Preview, confirm, commit. The preview and the commit carry the revision of the layer the draft started on, so a
 * file that changed since then is a conflict (409), never an overwrite. Apply is offered only for a preview without issues.
 */
export function PreviewDialog({
  draft,
  projectId,
  onApplied,
  onConflict,
  onClose,
}: {
  draft: Draft;
  projectId: string | null;
  onApplied: (result: CommitResult) => void;
  onConflict: () => void;
  onClose: () => void;
}) {
  const transport = useTransport();
  // a preview is applicable only for the draft it was made for: a changed draft shows none until its own arrives
  const [held, setHeld] = useState<{ draft: Draft; preview: Preview } | null>(null);
  const [failure, setFailure] = useState<{ draft: Draft; error: unknown } | null>(null);
  const preview = held && held.draft === draft ? held.preview : null;
  const error = failure && failure.draft === draft ? failure.error : null;
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      try {
        const next = await transport.request<Preview>("POST", `/v1/config/${encodeURIComponent(draft.module)}/preview${query(projectId)}`,
          previewRequest(draft));
        if (!cancelled) {
          setHeld({ draft, preview: next });
          setFailure(null);
        }
      } catch (caught) {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.code === "CONFIG_REVISION_CONFLICT") onConflict();
        else setFailure({ draft, error: caught });
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a new preview only for a new draft or "Preview again"
  }, [transport, draft, projectId, nonce]);

  async function apply(current: Preview) {
    const body: CommitRequest = { $schema: MUTATION_CONTRACT, kind: "commit_request", preview_id: current.preview_id,
      expected_revision: draft.revision, confirmed: current.confirm_required } as CommitRequest;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      const result = await transport.request<CommitResult>("PATCH",
        `/v1/config/${encodeURIComponent(draft.module)}/layers/${draft.layer}${query(projectId)}`, body);
      onApplied(result);
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "CONFIG_REVISION_CONFLICT") onConflict();
      else if (caught instanceof ApiError && caught.code === "PREVIEW_STALE") {
        setHeld(null);
        setNotice("The preview expired or the schema changed; it is being made again.");
        setNonce((value) => value + 1);
      } else if (caught instanceof ApiError && caught.code === "CONFIG_LOCKED") {
        setNotice("Another process holds the lock of the file. Try Apply again in a moment.");
      } else setFailure({ draft, error: caught });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dialog preview-dialog" role="dialog" aria-label="Preview of the change">
      <h3>
        Preview: {draft.module} · {draft.layer}
      </h3>
      {!preview && !error && <div className="muted">Computing the preview…</div>}
      {notice && <div className="cfg-notice" role="status">{notice}</div>}
      {error ? <ErrorPanel error={error} /> : null}
      {preview && (
        <>
          <div className="muted">{preview.file}</div>
          <table className="table diff-table">
            <thead>
              <tr>
                <th>Key</th>
                <th>Layer value</th>
                <th>Effective</th>
              </tr>
            </thead>
            <tbody>
              {preview.diff.map((item) => (
                <tr key={item.key}>
                  <td>{item.key}</td>
                  <td>
                    {shown(item.before)} → {shown(item.after)}
                  </td>
                  <td>
                    {shown(item.effective_before.value)} ({item.effective_before.layer ?? "unset"}) → {shown(item.effective_after.value)} (
                    {item.effective_after.layer ?? "unset"})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {preview.issues.length > 0 && (
            <ul className="issues" role="alert">
              {preview.issues.map((issue, index) => (
                <li key={`${issue.key}-${index}`}>
                  <code>{issue.key}</code> {issue.code}: {issue.message}
                </li>
              ))}
            </ul>
          )}
          {preview.confirm_required && (
            <div className="cfg-confirm">
              <strong>Confirmation required:</strong>
              <ul>
                {preview.confirm_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="buttons">
            <button type="button" disabled={busy || preview.issues.length > 0} onClick={() => void apply(preview)}>
              {preview.confirm_required ? "Confirm and apply" : "Apply"}
            </button>
          </div>
        </>
      )}
      <div className="buttons">
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
