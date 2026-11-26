import type { Bootstrap } from "../contracts";

/** The host protocol this frontend speaks. */
export const GUI_PROTOCOL = 1;

/** Contracts this frontend reads; the backend must serve each in this major version. */
export const REQUIRED_CONTRACTS: Array<[string, string]> = [
  ["urn:swissknifeman:gui:bootstrap", "v1"],
  ["urn:swissknifeman:gui:api-error", "v1"],
  ["urn:swissknifeman:gui:catalog", "v1"],
  ["urn:swissknifeman:gui:view-data", "v1"],
  ["urn:swissknifeman:gui:project", "v1"],
  ["urn:swissknifeman:gui:run", "v1"],
  ["urn:swissknifeman:gui:run-api", "v1"],
  ["urn:swissknifeman:gui:stream", "v1"],
];

/** Why the backend cannot serve this frontend, or `null` when it can. */
export function incompatibility(bootstrap: Bootstrap): string | null {
  const min = Number(bootstrap.gui_protocol.min);
  const max = Number(bootstrap.gui_protocol.max);
  if (!(min <= GUI_PROTOCOL && GUI_PROTOCOL <= max)) {
    return `the frontend speaks protocol ${GUI_PROTOCOL}, the backend ${min}–${max}`;
  }
  const served = new Set(bootstrap.contracts.map((entry) => `${entry.id}:${entry.version}`));
  const missing = REQUIRED_CONTRACTS.filter(([id, version]) => !served.has(`${id}:${version}`));
  if (missing.length) return `the backend does not serve ${missing.map(([id, v]) => `${id}:${v}`).join(", ")}`;
  return null;
}
