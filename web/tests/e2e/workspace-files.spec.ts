import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import type { Readable } from "node:stream";

// The P12.08 harness supplies @playwright/test, baseURL and an authenticated
// browser state (or SKM_E2E_TOKEN). Vitest also discovers *.spec.ts in P12.03.
const scenario = "create a workspace and project, upload a file and verify its downloaded bytes";
if (process.env.VITEST) {
  const { test } = await import("vitest");
  test.skip(scenario + " (Playwright, P12.08)");
} else {
  const { test } = createRequire(import.meta.url)("@playwright/test");
  interface Locator {
    getByRole(role: string, options: { name: string; exact?: boolean }): Locator;
    getByLabel(name: string, options?: { exact: boolean }): Locator;
    click(): Promise<void>;
    fill(value: string): Promise<void>;
    setInputFiles(file: { name: string; mimeType: string; buffer: Buffer }): Promise<void>;
  }
  interface Page extends Locator {
    goto(url: string): Promise<unknown>;
    waitForEvent(event: "download"): Promise<{ suggestedFilename(): string; createReadStream(): Promise<Readable> }>;
  }
  test(scenario, async ({ page }: { page: Page }) => {
    const slug = "ws-" + randomUUID().slice(0, 12);
    const token = process.env.SKM_E2E_TOKEN;
    await page.goto("/w/personal?view=workspaces" + (token ? "#token=" + encodeURIComponent(token) : ""));
    await page.getByRole("button", { name: "Создать пространство" }).click();
    const workspace = page.getByRole("dialog", { name: "Создать пространство" });
    await workspace.getByLabel("Slug").fill(slug);
    await workspace.getByLabel("Название").fill(slug);
    await workspace.getByRole("button", { name: "Создать", exact: true }).click();
    await page.getByRole("link", { name: slug, exact: true }).click();

    await page.getByRole("button", { name: "Создать проект" }).click();
    const project = page.getByRole("dialog", { name: "Создать проект" });
    await project.getByLabel("Slug").fill("maps");
    await project.getByLabel("Название").fill("Maps");
    await project.getByRole("button", { name: "Создать", exact: true }).click();
    await page.getByRole("link", { name: "Maps", exact: true }).click();
    await page.getByRole("tab", { name: "Files", exact: true }).click();

    const bytes = Buffer.from("SKM file round trip\nКарты\n", "utf8");
    await page.getByRole("button", { name: "Загрузить файл" }).click();
    const upload = page.getByRole("dialog", { name: "Загрузить файл" });
    await upload.getByLabel("Файл", { exact: true }).setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: bytes });
    await upload.getByRole("button", { name: "Загрузить файл" }).click();
    await page.getByRole("link", { name: "notes.txt" }).click();
    const [download] = await Promise.all([
      page.waitForEvent("download"), page.getByRole("button", { name: "Скачать" }).click(),
    ]);
    assert.equal(download.suggestedFilename(), "notes.txt");
    const chunks: Buffer[] = [];
    for await (const chunk of await download.createReadStream()) chunks.push(Buffer.from(chunk));
    const received = Buffer.concat(chunks);
    assert.deepEqual(received, bytes);
    assert.equal(createHash("sha256").update(received).digest("hex"), createHash("sha256").update(bytes).digest("hex"));
  });
}
