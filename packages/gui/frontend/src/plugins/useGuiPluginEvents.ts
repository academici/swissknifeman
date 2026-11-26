import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTransport } from "../transport/context";
import { invalidatePlugins } from "./api";

/** Subscribes to `gui.plugin.*` (state and grant changes) and refreshes the plugin queries and the catalog. */
export function useGuiPluginEvents(): void {
  const transport = useTransport();
  const queryClient = useQueryClient();
  useEffect(() => {
    const refresh = () => invalidatePlugins(queryClient);
    const subscription = transport.subscribe({ types: ["gui.plugin.*"] }, { onFrame: refresh, onSnapshotRequired: refresh });
    return () => subscription.close();
  }, [queryClient, transport]);
}
