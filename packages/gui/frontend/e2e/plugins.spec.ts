import { writeFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { api, origin, signIn } from "./session";

// One throwaway backend, one external extension (tests/fixtures/extensions/ext-demo, connected by [aicore.plugins] in
// backend.ts), four scenarios in order: each starts in the state the one before left (compatible, enabled, enabled ->
// disabled, then Enable again). Waits are on the screen, never on time.

const nav = (page: Page) => page.getByRole("navigation");
const state = (page: Page) => page.locator("h1 .status");

async function openPlugin(page: Page) {
  await nav(page).getByRole("link", { name: "Plugins", exact: true }).click();
  await page.getByRole("link", { name: "ext-demo", exact: true }).click();
  await expect(page.getByRole("heading", { name: /ext-demo/ })).toBeVisible();
}

async function grant(page: Page, effect: string) {
  await page.getByRole("button", { name: "Grant for ext-demo" }).click();
  const dialog = page.getByRole("dialog", { name: "Grant for ext-demo" });
  await dialog.getByLabel("Effect").selectOption(effect);
  await dialog.getByLabel("Expires").selectOption({ label: "1 day" });
  await dialog.getByRole("button", { name: "Grant", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: `Grant ${effect} to ext-demo` });
  await expect(confirm).toContainText("every project");
  await confirm.getByRole("button", { name: "Confirm and grant" }).click();
  await expect(page.getByRole("region", { name: "Grants" }).getByRole("row", { name: new RegExp(`^${effect.replace(".", "\\.")}`) })).toBeVisible();
}

async function post(path: string, body: unknown): Promise<Response> {
  return fetch(`${origin()}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.GUI_E2E_SECRET}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

test.beforeAll(() => {
  // another spec (config.spec.ts) rewrites the machine layer of the configuration: connect the extension again
  writeFileSync(process.env.GUI_E2E_CONFIG_FILE ?? "", process.env.GUI_E2E_CONFIG_TEXT ?? "");
});

test.afterAll(async () => {
  // leave the shared backend as it was for the other specs
  await post("/v1/plugins/ext-demo:disable", { $schema: "urn:swissknifeman:gui:plugin-api:v1", kind: "action_request" });
});

test.describe.serial("an external extension", () => {
  test("is compatible and hidden until Enable, then its route appears without a reload", async ({ page }) => {
    await signIn(page);
    await nav(page).getByRole("link", { name: "Plugins", exact: true }).click();
    await expect(page.getByRole("row", { name: /ext-demo/ })).toContainText("compatible");
    await expect(nav(page).getByRole("link", { name: "Ext demo home" })).toHaveCount(0);
    await page.getByRole("link", { name: "ext-demo", exact: true }).click();
    await expect(state(page)).toHaveText("compatible");
    await page.getByRole("button", { name: "Enable ext-demo" }).click(); // runs the conformance check first
    await expect(state(page)).toHaveText("enabled", { timeout: 30_000 });
    await nav(page).getByRole("link", { name: "Ext demo home" }).click();
    await expect(page).toHaveURL(/\/x\/ext-demo\/home$/);
    await expect(page.getByText("alpha").first()).toBeVisible();
  });

  test("a command without a grant is refused, with a grant it runs", async ({ page }) => {
    await signIn(page);
    await nav(page).getByRole("link", { name: "Ext demo note" }).click();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("PERMISSION_DENIED");
    await openPlugin(page);
    await grant(page, "project.write");
    await nav(page).getByRole("link", { name: "Ext demo note" }).click();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
    await expect(page.locator("h1 .status")).toHaveText("succeeded");
  });

  test("Disable during a run asks first and cancels the run", async ({ page }) => {
    await signIn(page);
    await openPlugin(page);
    await grant(page, "process.spawn");
    await nav(page).getByRole("link", { name: "Ext demo slow" }).click();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
    const runId = page.url().split("/").at(-1) ?? "";
    await expect(page.getByTestId("log-stdout")).toContainText("tick 1");
    await openPlugin(page);
    await page.getByRole("button", { name: "Disable ext-demo" }).click();
    const dialog = page.getByRole("dialog", { name: "Disable ext-demo" });
    await expect(dialog).toContainText("1 active");
    await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(page.getByText("Disabled: 0 run(s) finished, 1 cancelled.")).toBeVisible({ timeout: 30_000 });
    await expect(state(page)).toHaveText("disabled");
    await expect(nav(page).getByRole("link", { name: "Ext demo home" })).toHaveCount(0);
    await expect.poll(async () => (await api<{ state: string }>(`/v1/runs/${runId}`)).state).toBe("cancelled");
  });

  test("three failures quarantine the plugin and Release brings it back", async ({ page }) => {
    await signIn(page);
    await openPlugin(page);
    await page.getByRole("button", { name: "Enable ext-demo" }).click();
    await expect(state(page)).toHaveText(/^(enabled|healthy)$/, { timeout: 30_000 });
    for (let call = 0; call < 3; call += 1) {
      const response = await post("/v1/queries/ext-demo.flaky", { context: {}, params: {} });
      expect(response.status).toBe(502);
    }
    await expect(state(page)).toHaveText("quarantined");
    await expect(nav(page).getByRole("link", { name: "Ext demo home" })).toHaveCount(0);
    await page.getByRole("button", { name: "Release ext-demo" }).click();
    await expect(state(page)).toHaveText("enabled");
    await expect(nav(page).getByRole("link", { name: "Ext demo home" })).toBeVisible();
  });
});
