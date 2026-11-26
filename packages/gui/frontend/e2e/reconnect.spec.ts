import { expect, test } from "@playwright/test";
import { signIn, ticks } from "./session";

test("a dropped event stream resumes without lost or repeated log chunks", async ({ page }) => {
  let dropped = false;
  let connections = 0;
  await page.routeWebSocket("**/v1/events", (ws) => {
    connections += 1;
    const server = ws.connectToServer();
    let logFrames = 0;
    server.onMessage((message) => {
      ws.send(message);
      if (!dropped && String(message).includes('"kind":"log"')) {
        logFrames += 1;
        if (logFrames === 15) {
          dropped = true;
          ws.close();
          server.close();
        }
      }
    });
    ws.onMessage((message) => server.send(message));
  });
  await signIn(page);
  await page.getByRole("link", { name: "Ticks" }).click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
  const log = page.getByTestId("log-stdout");
  await expect.poll(() => dropped, { timeout: 20_000 }).toBe(true);
  await expect(log).toContainText("tick 40", { timeout: 20_000 });
  expect(connections).toBeGreaterThanOrEqual(2);
  const seen = ticks((await log.textContent()) ?? "");
  expect(seen[0]).toBe(1);
  expect(seen).toEqual(seen.map((_, index) => index + 1));
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.locator("h1 .status")).toHaveText("cancelled", { timeout: 20_000 });
});
