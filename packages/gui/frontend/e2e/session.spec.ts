import { expect, test } from "@playwright/test";

test("the one-time URL signs in once and opens the dashboard", async ({ browser }) => {
  const url = process.env.GUI_E2E_URL ?? "";
  const first = await browser.newContext();
  const page = await first.newPage();
  await page.goto(url);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Fleet" })).toBeVisible();
  await expect(page.getByText("Demo ready")).toBeVisible();
  const cookies = await first.cookies();
  const session = cookies.find((cookie) => cookie.name === "skm_gui_session");
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Strict");
  await first.close();

  const second = await browser.newContext();
  const again = await second.newPage();
  const response = await again.goto(url);
  expect(response?.status()).toBe(401);
  await expect(again.getByText("Not signed in")).toBeVisible();
  await second.close();
});
