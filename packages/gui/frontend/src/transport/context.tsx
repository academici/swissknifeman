import { createContext, useContext } from "react";
import type { Transport } from "./Transport";

export const TransportContext = createContext<Transport | null>(null);

export function useTransport(): Transport {
  const transport = useContext(TransportContext);
  if (!transport) throw new Error("no Transport: wrap the app in TransportContext.Provider");
  return transport;
}
