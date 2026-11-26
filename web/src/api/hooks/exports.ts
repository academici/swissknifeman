import { useCallback } from "react";
import { useAuth } from "../../app/providers/AuthProvider";
import { api, segment } from "./workspace";

export function useRunReport() {
  const { transport } = useAuth();
  return useCallback(async (runId: string, signal: AbortSignal) => {
    const { data } = await transport.request<Blob>("GET", `${api}/runs/${segment(runId)}/report.md`, {
      responseType: "blob", signal,
    });
    signal.throwIfAborted();
    if (data.type.split(";", 1)[0] !== "text/markdown") throw new Error("Unexpected report format");
    return data;
  }, [transport]);
}
