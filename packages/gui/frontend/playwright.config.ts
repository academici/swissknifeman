import { defineConfig, devices } from "@playwright/test";

// The backend is started by e2e/backend.ts (global setup) with a throwaway SKM_HOME and HOME and the fixture units of
// packages/gui/tests/fixtures/units/e2e; the built frontend (npm run build) is what it serves.
export default defineConfig({
  testDir: "e2e",
  testMatch: "*.spec.ts",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  globalSetup: "./e2e/backend.ts",
  use: { ...devices["Desktop Chrome"], headless: true, trace: "off" },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
