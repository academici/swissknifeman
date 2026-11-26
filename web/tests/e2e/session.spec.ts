import type { CreateTokenResult } from "../../src/api/generated/access";
import { api, assertAccessible, expect, ownerToken, projectId, signIn, test } from "./fixtures";

test("signs in from the fragment, clears the session on server revocation and accepts a pasted token", async ({ page, request }) => {
  const token = await api<CreateTokenResult>(request, "POST", "/tokens", { name: "Revocable browser session" }, {
    idempotent: false,
  });
  await signIn(page, token.secret, `/p/${projectId()}`);
  await expect(page.getByRole("heading", { name: "M5 acceptance" })).toBeVisible();
  expect(await page.evaluate((secret) => sessionStorage.getItem("skm.token") === secret &&
    Object.values(localStorage).every((value) => !value.includes(secret)), token.secret)).toBe(true);
  expect(await page.context().cookies()).toEqual([]);

  const rejected = page.waitForResponse((response) => response.status() === 401 && response.url().includes("/api/v1/"));
  await api(request, "POST", `/tokens/${token.token_id}/revoke`);
  await page.getByRole("link", { name: "Входящие" }).first().click();
  await rejected;
  await expect(page).toHaveURL(/\/login$/);
  await assertAccessible(page, "Вход в SKM");
  expect(await page.evaluate(() => sessionStorage.getItem("skm.token"))).toBeNull();
  await expect(page.getByRole("heading", { name: "M5 acceptance" })).toHaveCount(0);

  const me = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/me" && response.ok());
  await page.getByLabel("Токен доступа").fill(ownerToken());
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await me;
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("navigation").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Входящие" }).first()).toBeVisible();

  // Revisit the previously loaded query in the same SPA while holding its new snapshot.
  const snapshot = `**/api/v1/projects/${projectId()}`;
  let release!: () => void;
  const resume = new Promise<void>((resolve) => { release = resolve; });
  await page.route(snapshot, async (route) => {
    await resume;
    await route.continue();
  });
  const fresh = page.waitForRequest(snapshot);
  try {
    await page.evaluate((path) => {
      history.pushState(history.state, "", path);
      window.dispatchEvent(new PopStateEvent("popstate", { state: history.state }));
    }, `/p/${projectId()}`);
    await fresh;
    await expect(page.getByRole("heading", { name: "M5 acceptance" })).toHaveCount(0);
  } finally {
    release();
  }
  await expect(page.getByRole("heading", { name: "M5 acceptance" })).toBeVisible();
});
