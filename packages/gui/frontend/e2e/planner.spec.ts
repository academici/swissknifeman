import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { origin, signIn } from "./session";

// The plan is a copy of tests/fixtures/plans/e2e in the throwaway project; the directory name is that of the fixture.
const PLAN_DIR = "2026.10.05-№1-DEMO";

const project = () => process.env.GUI_E2E_PROJECT ?? "";
const itemFile = () => join(project(), "plans", PLAN_DIR, "phases", "P1", "P1.1.json");
const item = () => JSON.parse(readFileSync(itemFile(), "utf8")) as { summary: string; title: string; review: { reviewer: { provider: string; model: string } } };

/** The planner command line, as the bridge calls it: the hub umbrella in the project folder. */
function planner(...args: string[]): { ok: boolean; data?: Record<string, unknown> } {
  const out = execFileSync(process.env.GUI_E2E_UMBRELLA ?? "", ["planner", "--output", "json", ...args], {
    cwd: project(), encoding: "utf8", env: { PATH: process.env.PATH ?? "/usr/bin:/bin", HOME: process.env.GUI_E2E_HOME ?? "" },
  });
  return JSON.parse(out) as { ok: boolean; data?: Record<string, unknown> };
}

async function projectId(page: Page): Promise<string> {
  await page.locator('a[href="/projects"]').click();
  await page.getByRole("link", { name: "project", exact: true }).click();
  await page.getByRole("link", { name: "Plans" }).click();
  await page.getByRole("link", { name: /E2E demo plan/ }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  return new URL(page.url()).searchParams.get("project") ?? "";
}

async function save(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Save" }).click();
  const confirm = page.getByRole("button", { name: "Confirm and save" });
  await expect(page.getByText("Saved.").or(confirm)).toBeVisible();
  if (await confirm.isVisible()) await confirm.click();
  await expect(page.getByText("Saved.")).toBeVisible();
}

test("plans, board and item lead to the form; changing the reviewer model changes the plan file and the plan stays valid", async ({ page }) => {
  await signIn(page);
  const id = await projectId(page);
  await page.goto(`${origin()}/x/gui-planner/plans/PLAN1/board?project=${id}`);
  await expect(page.getByLabel("To do, 1")).toBeVisible();
  await page.getByRole("link", { name: "P1.1" }).click();
  await page.getByRole("link", { name: "Edit this item" }).click();

  const picker = page.getByRole("combobox", { name: "review/reviewer/model" });
  await expect(picker).toHaveValue("codex/gpt-6.1-sol");
  await picker.selectOption("claude-code/sonnet");
  await save(page);

  expect(item().review.reviewer).toMatchObject({ provider: "claude-code", model: "sonnet" });
  const check = planner("check", "PLAN1", "--json");
  expect(check.ok).toBe(true);
  expect(check.data?.errors).toBe(0);
});

test("a change made outside while the form is open is a conflict; Reapply saves my change on the new revision", async ({ page }) => {
  await signIn(page);
  const id = await projectId(page);
  await page.goto(`${origin()}/x/gui-planner/plans/PLAN1/items/P1.1/edit?project=${id}`);
  const summary = page.getByLabel("summary", { exact: true });
  await expect(summary).toBeVisible();
  await summary.fill("Summary from the browser");

  planner("set", "PLAN1", "P1.1", "--json", JSON.stringify({ title: "Title from outside" }));

  await page.getByRole("button", { name: "Save" }).click();
  const confirm = page.getByRole("button", { name: "Confirm and save" });
  const dialog = page.getByRole("dialog", { name: "The plan changed" });
  await expect(dialog.or(confirm)).toBeVisible();
  if (await confirm.isVisible()) await confirm.click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Reapply" }).click();
  const again = page.getByRole("button", { name: "Confirm and save" });
  await expect(page.getByText("Saved.").or(again)).toBeVisible();
  if (await again.isVisible()) await again.click();
  await expect(page.getByText("Saved.")).toBeVisible();

  expect(item()).toMatchObject({ summary: "Summary from the browser", title: "Title from outside" });
  expect(planner("check", "PLAN1", "--json").data?.errors).toBe(0);
});
