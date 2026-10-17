import { expect, test } from "@playwright/test";
import { api, signIn } from "./session";

test("greet runs as a dry run and for real, with its log", async ({ page }) => {
  await signIn(page);
  await page.locator('a[href="/projects"]').click();
  await page.getByRole("link", { name: "project", exact: true }).click();
  await page.getByRole("link", { name: "Greet" }).click();
  await page.getByLabel("Name *").fill("World");
  await page.getByRole("button", { name: "Dry run" }).click();
  await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
  await expect(page.getByTestId("log-stdout")).toHaveText("would greet World (dry run)\n");
  await expect(page.locator("h1 .status")).toHaveText("succeeded");

  await page.goBack();
  await page.getByLabel("Name *").fill("World");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
  await expect(page.getByTestId("log-stdout")).toHaveText("hello World\n");
  await expect(page.locator("h1 .status")).toHaveText("succeeded");
  const runId = page.url().split("/").at(-1) ?? "";
  const run = await api<{ state: string; dry_run: boolean }>(`/v1/runs/${runId}`);
  expect(run).toMatchObject({ state: "succeeded", dry_run: false });
});
