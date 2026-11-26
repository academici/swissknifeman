import { randomUUID } from "node:crypto";
import type { Page, Response } from "@playwright/test";
import type { CreatePlanResult, OpenDraftResult } from "../../src/api/generated/planning";
import { api, assertAccessible, expect, projectId, responseFor, signIn, test, viewerToken } from "./fixtures";

async function expectProblem(page: Page, response: Response, status: number, code: string, title: string) {
  expect(response.status()).toBe(status);
  const problem = await response.json() as { code: string; request_id: string };
  expect(problem).toMatchObject({ code, request_id: expect.any(String) });
  const panel = page.getByRole("alert").filter({ has: page.getByRole("heading", { name: title, exact: true }) }).first();
  await expect(panel.getByText(code, { exact: true })).toBeVisible();
  await expect(panel.getByText(problem.request_id, { exact: true })).toBeVisible();
}

test("a viewer has no write controls and receives an accessible 403 problem", async ({ page, request }) => {
  const token = await viewerToken(request);
  await signIn(page, token, `/p/${projectId()}/plans`);
  await assertAccessible(page, "Планы");
  await expect(page.getByRole("button", { name: "Создать план" })).toHaveCount(0);
  await page.goto(`/p/${projectId()}/files`);
  await assertAccessible(page, "Файлы");
  await expect(page.getByRole("button", { name: "Загрузить файл" })).toHaveCount(0);

  const response = responseFor(page, "GET", "/api/v1/config/explain");
  await page.goto("/settings?scope=instance");
  await expectProblem(page, await response, 403, "FORBIDDEN", "Нет доступа");
});

test("shows the request ID for a missing plan", async ({ page }) => {
  const missing = randomUUID();
  const response = responseFor(page, "GET", `/api/v1/plans/${missing}`);
  await signIn(page, undefined, `/plans/${missing}`);
  await expectProblem(page, await response, 404, "NOT_FOUND", "Не найдено");
  await assertAccessible(page, "План");
});

test("shows a conflict when saving over a newer draft version", async ({ page, request }) => {
  const plan = await api<CreatePlanResult>(request, "POST", `/projects/${projectId()}/plans`, { title: "Concurrent draft" });
  const draft = await api<OpenDraftResult>(request, "POST", `/plans/${plan.plan_id}/drafts`, { base: "empty" });
  const path = `/plans/${plan.plan_id}/drafts/${draft.draft_id}`;
  await signIn(page, undefined, path);
  await page.getByRole("button", { name: "+ Phase", exact: true }).click();
  await page.getByRole("textbox", { name: "title", exact: true }).fill("Browser change");

  // Establish the stale edit version after the client has read the draft and before its PATCH is forwarded.
  await page.route(`**/api/v1${path}`, async (route) => {
    if (route.request().method() === "PATCH") {
      await api(request, "PATCH", path, { title: "Server change" }, {
        headers: { "If-Match": 'W/"v1"', "Content-Type": "application/merge-patch+json" },
      });
    }
    await route.continue();
  });
  const response = responseFor(page, "PATCH", `/api/v1${path}`);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expectProblem(page, await response, 409, "VERSION_CONFLICT", "Конфликт изменений");
  const panel = page.getByRole("alert").filter({ has: page.getByRole("heading", { name: "Конфликт изменений" }) });
  await expect(panel.getByRole("heading", { name: "Ваша версия" })).toBeVisible();
  await panel.getByText("Подробности", { exact: true }).first().click();
  await expect(panel.getByText(/Browser change/)).toBeVisible();
  await expect(panel.getByRole("button", { name: "Загрузить текущую версию" })).toBeEnabled();
});
