import type { Trust } from "../contracts/generated/plugin-api";

const DIGEST = `sha256:${"1".repeat(64)}`;

export function trust(id: string, over: Partial<Trust> = {}): Trust {
  return {
    $schema: "urn:swissknifeman:gui:trust:v1",
    id,
    source: "extension",
    state: "healthy",
    runtime_enabled: true,
    ui_enabled: true,
    manifest_digest: DIGEST,
    compatibility: { protocol_ok: true, missing_contracts: [] },
    failures: { count: 0, window_s: 300 },
    permissions: [],
    grants: [],
    ...over,
  };
}
