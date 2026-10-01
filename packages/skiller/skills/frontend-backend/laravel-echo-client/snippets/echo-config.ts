// Source: anonymized production project
//
// Single point of creation Echo-instance per client session.
// The config is collected by priority: runtime (from the server) -> env (assembly) -> default.
// Runtime-the config is updated from backend to the browser (Inertia-prop / shared-data /
// built-in <script>), which allows you to change the environment WITHOUT rebuilding the front.

import Echo from "laravel-echo";

let isEchoInitialized = false;

/** What comes from the server to the browser (for example, page.props.broadcasting). */
type RuntimeWebsocketConfig = {
  enabled: boolean;
  app_key: string | null;
  host: string | null;
  port: number | null;
  wss_port: number | null;
  scheme: string | null;
  path: string | null;
};

function resolveEchoConfig(runtimeConfig?: RuntimeWebsocketConfig) {
  // Layer env — defaults at the build stage.
  const config = {
    key: import.meta.env.VITE_REVERB_APP_KEY ?? "app",
    wsHost: import.meta.env.VITE_REVERB_HOST ?? window.location.hostname,
    wsPort: Number(import.meta.env.VITE_REVERB_PORT ?? 8080),
    wssPort: Number(import.meta.env.VITE_REVERB_PORT ?? 443),
    scheme: import.meta.env.VITE_REVERB_SCHEME ?? "http",
    path: undefined as string | undefined,
  };

  if (!runtimeConfig?.enabled) {
    return config;
  }

  // Layer runtime overlaps env — but only with non-empty fields.
  if (runtimeConfig.app_key) config.key = runtimeConfig.app_key;
  if (runtimeConfig.host) config.wsHost = runtimeConfig.host;
  if (runtimeConfig.port !== null) config.wsPort = runtimeConfig.port;
  if (runtimeConfig.wss_port !== null) config.wssPort = runtimeConfig.wss_port;
  if (runtimeConfig.scheme) config.scheme = runtimeConfig.scheme;
  if (runtimeConfig.path) config.path = runtimeConfig.path;

  return config;
}

/** Idempotent: creates Echo once per session, then - no-op. */
export function ensureEchoConnection(runtimeConfig?: RuntimeWebsocketConfig): void {
  if (isEchoInitialized || !runtimeConfig?.enabled) {
    return;
  }

  const config = resolveEchoConfig(runtimeConfig);

  window.echo = new Echo({
    broadcaster: "reverb", // 'pusher' for Pusher/compatible backend
    key: config.key,
    wsHost: config.wsHost,
    wsPort: config.wsPort,
    wssPort: config.wssPort,
    forceTLS: config.scheme === "https",
    wsPath: config.path,
    enabledTransports: ["ws", "wss"],
  });

  isEchoInitialized = true;
}

/** Close connection on logout / transition in guest-context. */
export function disconnectEchoConnection(): void {
  if (!isEchoInitialized || !window.echo) {
    return;
  }

  window.echo.disconnect();
  isEchoInitialized = false;
}
