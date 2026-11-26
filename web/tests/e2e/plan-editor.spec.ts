import type { APIRequestContext, Page } from "@playwright/test";
import type {
  AddFileDefsStagedBlobRef, AddFileResult, AddFileVersionResult, GetFileView,
} from "../../src/api/generated/artifacts";
import type { DraftView, PublicationPreviewView, PublishRevisionResult, SaveDraftResult } from "../../src/api/generated/planning";
import { api, expect, projectId, responseFor, signIn, test, workspaceId } from "./fixtures";

const previewPath = /\/drafts\/[^/]+\/publication-preview$/;
const publishPath = /\/drafts\/[^/]+\/publish$/;
const editor = (page: Page) => page.getByRole("region", { name: "Поля сущности" });

async function save(page: Page, version: number): Promise<SaveDraftResult> {
  const saved = responseFor(page, "PATCH", /\/drafts\/[^/]+$/);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const response = await saved;
  expect(response.request().headers()["if-match"]).toBe(`W/"v${version}"`);
  expect(response.request().headers()["content-type"]).toBe("application/merge-patch+json");
  expect(response.ok(), await response.text()).toBe(true);
  return await response.json() as SaveDraftResult;
}

async function stage(request: APIRequestContext, content: string) {
  return api<AddFileDefsStagedBlobRef>(
    request, "POST", `/workspaces/${workspaceId()}/blobs?media_type=text%2Fplain`, Buffer.from(content),
    { headers: { "Content-Type": "application/octet-stream" } },
  );
}

async function addMaterial(request: APIRequestContext, draftPath: string) {
  const file = await api<AddFileResult>(request, "POST", `/projects/${projectId()}/files`, {
    workspace_id: workspaceId(), project_id: projectId(), title: "Acceptance notes", origin: "upload",
    original_filename: "notes.txt", source: { kind: "upload" },
    blob: await stage(request, "Acceptance notes, first version.\n"),
  });
  const draft = await api<DraftView>(request, "GET", draftPath);
  await api<SaveDraftResult>(request, "PATCH", draftPath, {
    materials: [{
      key: "notes", title: "Acceptance notes", kind: "file_version", file_version_id: file.file_version_id,
      role: "input", required_for: ["execution"], freshness: { policy: "latest_at_publish" },
      applies_to: ["P1.1"],
    }],
  }, {
    headers: { "If-Match": `W/"v${draft.edit_version}"`, "Content-Type": "application/merge-patch+json" },
  });
  return file;
}

test("edits a template, confirms exact publication pins and compares r2 with r1", async ({ page, request }) => {
  await signIn(page, undefined, `/p/${projectId()}/plans`);
  await page.getByRole("button", { name: "Создать план", exact: true }).click();
  const create = page.getByRole("dialog", { name: "Создать план" });
  await create.getByRole("textbox", { name: "Название плана" }).fill("Template acceptance");
  await create.getByRole("combobox", { name: "Шаблон" }).selectOption("feature");
  await create.getByRole("textbox", { name: "title", exact: true }).fill("Template acceptance");
  await create.getByRole("textbox", { name: "goal", exact: true }).fill("Exercise publishing with a versioned input");
  await create.getByRole("button", { name: "Создать", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Редактор черновика" })).toBeVisible();

  await page.getByRole("button", { name: "+ Item", exact: true }).click();
  await editor(page).getByRole("textbox", { name: "title", exact: true }).fill("New acceptance item");
  await editor(page).getByRole("combobox", { name: "executor", exact: true }).selectOption("light");
  await editor(page).getByRole("combobox", { name: "verification_intensity" }).selectOption("heavy");
  await page.getByRole("button", { name: "+ Check", exact: true }).click();
  await expect(editor(page).getByRole("textbox", { name: "owner", exact: true })).toHaveValue("P1.2");
  const validation = page.waitForResponse((response) => {
    const request = response.request();
    return request.method() === "POST" && /\/drafts\/[^/]+\/validate$/.test(new URL(response.url()).pathname)
      && request.postDataJSON().expected_edit_version === 2;
  });
  const saved = await save(page, 1);
  const validated = await validation;
  expect(validated.ok()).toBe(true);
  expect(validated.request().postDataJSON()).toMatchObject({ expected_edit_version: saved.edit_version });
  await expect(page.getByRole("region", { name: "Findings" })).toBeVisible();

  const draftUrl = new URL(page.url()).pathname;
  const file = await addMaterial(request, draftUrl);
  await page.reload();
  const firstPreview = responseFor(page, "POST", previewPath);
  await page.getByRole("button", { name: "Publish…", exact: true }).click();
  const publication = page.getByRole("dialog", { name: "Публикация черновика" });
  const first = await (await firstPreview).json() as PublicationPreviewView;
  expect(first.publishable, JSON.stringify(first.validation)).toBe(true);
  expect(first.pinned_materials).toEqual([expect.objectContaining({ file_version_id: file.file_version_id })]);
  await expect(publication.getByRole("heading", { name: "Зафиксированные версии материалов" })).toBeVisible();
  await publication.getByRole("textbox", { name: "Причина публикации" }).fill("Verify current material pin");
  const confirm = publication.getByRole("button", { name: "Publish shown changes" });

  const currentFile = await api<GetFileView>(request, "GET", `/files/${file.file_id}`);
  const nextFile = await api<AddFileVersionResult>(request, "POST", `/files/${file.file_id}/versions`, {
    blob: await stage(request, "Acceptance notes, revised.\n"),
    declared_media_type: "text/plain", original_filename: "notes.txt", source: { kind: "upload" },
  }, { headers: { "If-Match": `W/"v${currentFile.row_version}"` } });

  const rejected = responseFor(page, "POST", publishPath);
  await confirm.click();
  const conflict = await rejected;
  expect(conflict.status()).toBe(409);
  expect(conflict.request().postDataJSON()).toMatchObject({ expected_content_digest: first.content_digest });
  expect(await conflict.json()).toMatchObject({ code: "VERSION_CONFLICT", details: { reason: "candidate_changed" } });
  await expect(publication.getByRole("alert")).toContainText("Prepared content changed");
  await expect(confirm).toBeDisabled();

  const refreshed = responseFor(page, "POST", previewPath);
  await publication.getByRole("button", { name: "Refresh preview" }).click();
  const fresh = await (await refreshed).json() as PublicationPreviewView;
  expect(fresh.content_digest).not.toBe(first.content_digest);
  expect(fresh.pinned_materials).toEqual([expect.objectContaining({ file_version_id: nextFile.file_version_id })]);
  const r1Response = responseFor(page, "POST", publishPath);
  await confirm.click();
  const r1 = await r1Response;
  expect(r1.status()).toBe(201);
  expect(r1.request().postDataJSON()).toMatchObject({ expected_content_digest: fresh.content_digest });
  expect(r1.request().headers()["idempotency-key"]).not.toBe(conflict.request().headers()["idempotency-key"]);
  expect(await r1.json() as PublishRevisionResult).toMatchObject({ revision_no: 1 });
  await publication.getByRole("link", { name: "ревизия r1" }).click();

  await page.getByRole("button", { name: "Открыть черновик" }).click();
  const tree = page.getByRole("region", { name: "Дерево плана" });
  await tree.locator("summary").filter({ hasText: "P1 · Implementation" }).click();
  await page.getByRole("button", { name: /P1\.1 · Template acceptance/ }).click();
  await editor(page).getByRole("textbox", { name: "title", exact: true }).fill("Revised acceptance item");
  await save(page, 1);
  await page.reload();
  await page.getByRole("button", { name: "Publish…", exact: true }).click();
  await publication.getByRole("textbox", { name: "Причина публикации" }).fill("Revise item title");
  await expect(confirm).toBeEnabled();
  const nextRevision = responseFor(page, "POST", publishPath);
  await confirm.click();
  const r2 = await nextRevision;
  expect(r2.status()).toBe(201);
  expect(await r2.json() as PublishRevisionResult).toMatchObject({ revision_no: 2 });
  await publication.getByRole("link", { name: "ревизия r2" }).click();
  await page.getByRole("tab", { name: "Ревизии" }).click();
  await page.getByRole("link", { name: "Сравнить с родительской" }).click();
  await expect(page.getByRole("heading", { name: "Сравнение ревизий" })).toBeVisible();
  await expect(page.getByText("Revised acceptance item", { exact: false }).first()).toBeVisible();
});
