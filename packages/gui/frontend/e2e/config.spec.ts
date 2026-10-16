import { writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { api, origin, signIn } from "./session";

interface View {
  layers: Array<{ name: string; file: string | null; revision: string | null }>;
}

test("edit, preview, confirm and apply; then an outside change is a conflict that Reapply resolves", async ({ page }) => {
  await signIn(page);
  await page.goto(`${origin()}/settings/config/demo?layer=machine`);
  const field = page.getByLabel("greeting_repeat", { exact: true });
  await expect(field).toBeVisible();

  // Edit → Preview → confirm (machine layer) → Apply.
  await field.fill("3");
  await page.getByRole("button", { name: "Preview (1)" }).click();
  const dialog = page.getByRole("dialog", { name: "Preview of the change" });
  await expect(dialog.getByText("machine_layer")).toBeVisible();
  await dialog.getByRole("button", { name: "Confirm and apply" }).click();
  const badge = page.getByTestId("prov-greeting_repeat");
  await expect(badge).toContainText("machine");
  await expect(badge).toContainText("3");

  // The file changes outside the GUI while a draft is open.
  await field.fill("4");
  const view = await api<View>("/v1/config/demo/effective");
  const machine = view.layers.find((layer) => layer.name === "machine");
  expect(machine?.file).toBeTruthy();
  writeFileSync(machine?.file ?? "", "schema_version = 1\n\n[demo]\ngreeting_repeat = 9\n");

  await page.getByRole("button", { name: "Preview (1)" }).click();
  const conflict = page.getByRole("dialog", { name: "The file changed" });
  await expect(conflict.getByText("conflict")).toBeVisible();
  await conflict.getByRole("button", { name: "Reapply" }).click();
  const second = page.getByRole("dialog", { name: "Preview of the change" });
  await second.getByRole("button", { name: "Confirm and apply" }).click();
  await expect(badge).toContainText("4");
  await expect(badge).toContainText("machine");
});
