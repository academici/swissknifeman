import { Component, type ReactNode } from "react";
import { ApiError } from "../transport/ApiError";

export function ErrorPanel({ error, title }: { error: unknown; title?: string }) {
  const api = error instanceof ApiError ? error : null;
  return (
    <div className="error-panel" role="alert">
      <strong>{title ?? "Request failed"}</strong>
      <div className="error-code">{api ? api.code : "ERROR"}</div>
      <div>{error instanceof Error ? error.message : String(error)}</div>
      {api && api.issues.length > 0 && (
        <ul className="issues">
          {api.issues.map((issue) => (
            <li key={`${issue.pointer}-${issue.code}`}>
              <code>{issue.pointer || "/"}</code> {issue.code}: {issue.message}
            </li>
          ))}
        </ul>
      )}
      {api?.correlationId && <div className="muted">correlation id {api.correlationId}</div>}
    </div>
  );
}

interface State {
  error: unknown;
}

/** Last line of defence: an unexpected render error shows its code, message and correlation id. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error };
  }

  override render() {
    if (this.state.error) return <ErrorPanel error={this.state.error} title="Something went wrong" />;
    return this.props.children;
  }
}
