import type { Page } from "@playwright/test";
import { expect, projectId, responseFor, signIn, test } from "./fixtures";

const review = "execution.review.max_rounds";
const search = (page: Page) => page.getByRole("searchbox", { name: "Поиск настроек" });
const field = (page: Page) => page.getByRole("spinbutton", { name: review, exact: true });
const row = (page: Page) => page.getByRole("article", { name: review, exact: true });
const conflictRequest = /\/api\/v1\/config\/entries\/[^/]+\/execution\.review\.max_rounds$/;

async function openSettings(page: Page) {
  await signIn(page, undefined, `/settings?scope=project:${projectId()}`);
  await search(page).fill(review);
  await expect(field(page)).toBeEnabled();
}

async function apply(page: Page) {
  const opened = responseFor(page, "POST", "/api/v1/config/import");
  await page.getByRole("button", { name: "Предпросмотр", exact: true }).click();
  const dryRun = await opened;
  expect(dryRun.ok()).toBe(true);
  expect(dryRun.request().postDataJSON()).toMatchObject({
    dry_run: true,
    scope: { level: "project", scope_id: projectId() },
  });
  const dialog = page.getByRole("dialog", { name: /Предпросмотр/ });
  await dialog.getByRole("textbox", { name: "Причина" }).fill("M5 review settings");
  const submitted = responseFor(page, "POST", "/api/v1/config/import");
  await dialog.getByRole("button", { name: "Применить", exact: true }).click();
  const response = await submitted;
  expect(response.ok()).toBe(true);
  expect(response.request().postDataJSON()).toMatchObject({
    dry_run: false,
    document: dryRun.request().postDataJSON().document,
    expected_entries_digest: dryRun.request().postDataJSON().expected_entries_digest,
  });
  await expect(dialog).toBeHidden();
}

async function submitRow(page: Page) {
  await row(page).getByRole("button", { name: "Сохранить только этот ключ" }).click();
  const dialog = page.getByRole("dialog", { name: /Сохранить ключ/ });
  await dialog.getByRole("button", { name: "Сохранить ключ", exact: true }).click();
}

test("previews and applies a project override, shows provenance and resolves a two-tab CAS conflict", async ({ page, context }) => {
  await openSettings(page);
  await field(page).fill("1");
  await apply(page);
  await expect(row(page).getByText(/Источник project.*\(v1\)/)).toBeVisible();

  await search(page).fill("worker.capacity");
  const hostOnly = page.getByRole("article", { name: "worker.capacity", exact: true });
  await expect(hostOnly.getByText(/Допустимые уровни instance, host/)).toBeVisible();
  await expect(hostOnly.getByRole("spinbutton", { name: "worker.capacity" })).not.toBeEditable();
  await expect(hostOnly.getByRole("button", { name: "Сохранить только этот ключ" })).toHaveCount(0);

  const second = await context.newPage();
  await openSettings(second);
  await search(page).fill(review);
  await expect(field(page)).toHaveValue("1");
  await expect(field(second)).toHaveValue("1");
  await field(page).fill("2");
  await field(second).fill("3");

  // Hold tab B's real PUT before it reaches SKM so both requests use the same row version.
  let onIntercept!: () => void;
  const intercepted = new Promise<void>((resolve) => { onIntercept = resolve; });
  let continueWrite!: () => void;
  const release = new Promise<void>((resolve) => { continueWrite = resolve; });
  await second.route((url) => conflictRequest.test(url.pathname), async (route) => {
    if (route.request().method() === "PUT") {
      onIntercept();
      await release;
    }
    await route.continue();
  }, { times: 1 });
  const rejected = responseFor(second, "PUT", conflictRequest);
  await submitRow(second);
  await intercepted;
  try {
    await apply(page);
  } finally {
    continueWrite();
  }

  const response = await rejected;
  expect(response.status()).toBe(409);
  expect(response.request().headers()["if-match"]).toBe('W/"v1"');
  expect(await response.json()).toMatchObject({ code: "VERSION_CONFLICT", request_id: expect.any(String) });

  const dialog = second.getByRole("dialog", { name: "Конфликт изменений" });
  await expect(dialog.getByRole("columnheader", { name: "Current" })).toBeVisible();
  await expect(dialog.getByRole("cell", { name: /v2 2/ })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Rebase draft" })).toBeDisabled();
  await dialog.getByRole("button", { name: `Take current · ${review}` }).click();
  await dialog.getByRole("button", { name: "Rebase draft" }).click();
  await expect(dialog).toBeHidden();
  await expect(field(second)).toHaveValue("2");
});
