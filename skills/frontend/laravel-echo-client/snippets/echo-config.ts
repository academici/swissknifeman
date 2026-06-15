// Source: anonymized production project
//
// Единственная точка создания Echo-инстанса за сессию клиента.
// Конфиг собирается по приоритету: runtime (с сервера) -> env (сборка) -> дефолт.
// Runtime-конфиг прокидывается с backend в браузер (Inertia-проп / shared-данные /
// встроенный <script>), что позволяет менять окружение БЕЗ пересборки фронта.

import Echo from "laravel-echo";

let isEchoInitialized = false;

/** То, что приходит с сервера в браузер (например, page.props.broadcasting). */
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
  // Слой env — дефолты на этапе сборки.
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

  // Слой runtime перекрывает env — но только непустыми полями.
  if (runtimeConfig.app_key) config.key = runtimeConfig.app_key;
  if (runtimeConfig.host) config.wsHost = runtimeConfig.host;
  if (runtimeConfig.port !== null) config.wsPort = runtimeConfig.port;
  if (runtimeConfig.wss_port !== null) config.wssPort = runtimeConfig.wss_port;
  if (runtimeConfig.scheme) config.scheme = runtimeConfig.scheme;
  if (runtimeConfig.path) config.path = runtimeConfig.path;

  return config;
}

/** Идемпотентно: создаёт Echo один раз за сессию, дальше — no-op. */
export function ensureEchoConnection(runtimeConfig?: RuntimeWebsocketConfig): void {
  if (isEchoInitialized || !runtimeConfig?.enabled) {
    return;
  }

  const config = resolveEchoConfig(runtimeConfig);

  window.echo = new Echo({
    broadcaster: "reverb", // 'pusher' для Pusher/совместимого бэкенда
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

/** Закрыть соединение при логауте / переходе в guest-контекст. */
export function disconnectEchoConnection(): void {
  if (!isEchoInitialized || !window.echo) {
    return;
  }

  window.echo.disconnect();
  isEchoInitialized = false;
}
