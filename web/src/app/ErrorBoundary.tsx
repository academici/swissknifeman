import { Component, type PropsWithChildren } from "react";
import { ErrorPanel } from "../components/feedback/ErrorPanel";

type BoundaryState = { failed: false } | { failed: true; error: unknown };

export class ErrorBoundary extends Component<PropsWithChildren, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(error: unknown): BoundaryState {
    return { failed: true, error };
  }

  render() {
    if (this.state.failed) return <ErrorPanel error={this.state.error} />;
    return this.props.children;
  }
}
