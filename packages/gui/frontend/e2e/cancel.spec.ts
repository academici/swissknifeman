import { expect, test } from "@playwright/test";
import { api, signIn } from "./session";

function groupAlive(pgid: number): boolean {
  try {
    process.kill(-pgid, 0);
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ESRCH") return false;
    throw error;
  }
}

test("cancel stops the whole process group", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Ticks" }).click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
  const log = page.getByTestId("log-stdout");
  await expect(log).toContainText("tick 3");
  const pgid = Number(/pgid (\d+)/.exec((await log.textContent()) ?? "")?.[1]);
  expect(pgid).toBeGreaterThan(1);
  expect(groupAlive(pgid)).toBe(true);
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.locator("h1 .status")).toHaveText("cancelled", { timeout: 20_000 });
  const runId = page.url().split("/").at(-1) ?? "";
  expect((await api<{ state: string }>(`/v1/runs/${runId}`)).state).toBe("cancelled");
  await expect.poll(() => groupAlive(pgid), { timeout: 10_000 }).toBe(false);
});
