import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  testMatch: "**/*.spec.ts",
  outputDir: "../.pytest_cache/playwright",
  globalSetup: "./tests/e2e/global-setup.ts",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  use: {
    browserName: "chromium",
    headless: true,
    serviceWorkers: "block",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    // The existing workspace spec uses the base Playwright fixtures.
    launchOptions: { args: ["--proxy-server=http://127.0.0.1:9"] },
  },
});
