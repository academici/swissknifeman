import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

function markdownChunkReport(): Plugin {
  return {
    name: "skm-markdown-chunk-report",
    apply: "build",
    generateBundle(_, bundle) {
      const files = Object.values(bundle).flatMap((output) =>
        output.type === "chunk" &&
        Object.keys(output.modules).some((id) => id.includes("/node_modules/react-markdown/"))
          ? [output.fileName]
          : [],
      );
      this.emitFile({
        type: "asset",
        fileName: ".vite/markdown-chunks.json",
        source: JSON.stringify(files),
      });
    },
  };
}

const backend = { target: "http://127.0.0.1:8765", changeOrigin: true };

export default defineConfig({
  base: "/",
  plugins: [react(), markdownChunkReport()],
  server: {
    proxy: {
      "/api": backend,
      "^/health/(live|ready|details)(\\?|$)": backend,
    },
  },
  build: { manifest: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    // Node 25+ defines its own global localStorage, which shadows jsdom's and is undefined without
    // --localstorage-file; the tests need the jsdom storage of the simulated page.
    poolOptions: { forks: { execArgv: ["--no-experimental-webstorage"] } },
  },
});
