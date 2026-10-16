import { useQuery } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import type { Bootstrap } from "../contracts";
import { useTransport } from "../transport/context";
import { GUI_PROTOCOL, incompatibility } from "./compat";
import { ErrorPanel } from "./ErrorView";

/** The handshake: the main UI opens only for a backend that speaks this frontend's protocol and contracts. */
export function BootstrapGate({ children }: { children: (bootstrap: Bootstrap) => ReactNode }) {
  const transport = useTransport();
  const query = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () => transport.request<Bootstrap>("GET", "/v1/bootstrap"),
    staleTime: Infinity,
  });
  useEffect(() => {
    if (query.data) transport.setEpoch(query.data.epoch);
  }, [query.data, transport]);
  if (query.isPending) return <div className="splash">Connecting to the SKM backend…</div>;
  if (query.isError) return <ErrorPanel error={query.error} title="The backend is not reachable" />;
  const problem = incompatibility(query.data);
  if (problem) {
    return (
      <div className="error-panel" role="alert">
        <strong>The backend and this frontend do not fit</strong>
        <div className="error-code">PROTOCOL_INCOMPATIBLE</div>
        <div>{problem}.</div>
        <div className="muted">
          frontend protocol {GUI_PROTOCOL}; backend {query.data.backend.version} (Python {query.data.backend.python}),
          protocol {query.data.gui_protocol.min}–{query.data.gui_protocol.max}
        </div>
      </div>
    );
  }
  return <>{children(query.data)}</>;
}
