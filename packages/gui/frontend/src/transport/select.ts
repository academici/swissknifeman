import { HttpTransport } from "./HttpTransport";
import { TauriTransport, tauriGlobal } from "./TauriTransport";
import type { Transport } from "./Transport";

/** Desktop shell (withGlobalTauri) or a plain browser. */
export function desktopMode(): boolean {
  return tauriGlobal() !== undefined;
}

export function selectTransport(): Transport {
  return desktopMode() ? new TauriTransport() : new HttpTransport();
}
