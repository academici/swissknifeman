import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The build must run under the backend CSP (script-src 'self', style-src 'self'): no inlined assets, no inline
// module-preload polyfill. `npm run dev` proxies /v1 (and the WebSocket) to a running `gui serve`.
declare const process: { env: Record<string, string | undefined> };
const backend = process.env.GUI_BACKEND ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
    assetsInlineLimit: 0,
    modulePreload: { polyfill: false },
    sourcemap: false,
  },
  server: {
    proxy: { "/v1": { target: backend, ws: true, changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
  },
});
