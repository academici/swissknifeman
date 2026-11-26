import { useDialog } from "../components/Dialog";
import { threeWay, type Draft } from "./draft";
import { formatValue } from "./ProvenanceBadge";
import type { Value } from "./types";

const LABEL = { same: "same", theirs: "theirs", conflict: "conflict" } as const;

/**
 * The file changed after the draft started. By key: base (the file when the draft started), current (the file now) and
 * mine (the draft). Reload drops the draft; Reapply makes a new preview of the draft on the current revision.
 */
export function ConflictView({
  draft,
  current,
  onReload,
  onReapply,
}: {
  draft: Draft;
  current: Record<string, Value | null>;
  onReload: () => void;
  onReapply: () => void;
}) {
  const states = threeWay(draft, current);
  const dialog = useDialog<HTMLDivElement>();
  return (
    <div className="dialog conflict-view" role="dialog" aria-label="The file changed" {...dialog}>
      <h3>The {draft.layer} file changed since you started</h3>
      <table className="table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Base</th>
            <th>Current</th>
            <th>Mine</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {states.map((state) => (
            <tr key={state.key} className={`status-${state.status}`}>
              <td>{state.key}</td>
              <td>{formatValue(state.base)}</td>
              <td>{formatValue(state.current)}</td>
              <td>{state.mine === undefined ? "" : formatValue(state.mine)}</td>
              <td>{LABEL[state.status]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="buttons">
        <button type="button" onClick={onReload}>
          Reload
        </button>
        <button type="button" onClick={onReapply}>
          Reapply
        </button>
      </div>
    </div>
  );
}
