import { queryOptions, useQuery } from "@tanstack/react-query";
import type { WhoAmIView } from "../generated/access";
import type { Transport } from "../transport";

export const whoAmIKey = ["access", "me"] as const;

export async function readWhoAmI(transport: Transport, signal: AbortSignal) {
  const { data } = await transport.request<WhoAmIView>("GET", "/api/v1/me", { signal });
  if (typeof data?.principal?.display_name !== "string") throw new Error("Invalid identity response");
  return data;
}

export function whoAmIOptions(transport: Transport) {
  return queryOptions({
    queryKey: whoAmIKey,
    queryFn: ({ signal }) => readWhoAmI(transport, signal),
  });
}

export function useWhoAmI(transport: Transport, enabled = true) {
  return useQuery({ ...whoAmIOptions(transport), enabled });
}
