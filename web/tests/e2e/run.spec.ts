import type { APIRequestContext, Locator, Page } from "@playwright/test";
import type { StartRunResult, ValidateForExecutionResult } from "../../src/api/generated/execution_08";
import type { HistoryPage } from "../../src/api/generated/execution_06";
import type { CreatePlanResult, PublicationPreviewView, PublishRevisionResult, SaveDraftResult } from "../../src/api/generated/planning";
import { api, expect, projectId, responseFor, signIn, test } from "./fixtures";

async function fillArray(group: Locator, values: readonly string[]) {
  for (const [index, value] of values.entries()) {
    await group.getByRole("button", { name: "Добавить элемент", exact: true }).click();
    await group.getByRole("textbox", { name: `Элемент ${index + 1}`, exact: true }).fill(value);
  }
}

async function seedCommandCheck(request: APIRequestContext, path: string, version: number) {
  const networkCheck = [
    "import socket",
    "try:",
    "    socket.socket()",
    "except PermissionError:",
    "    pass",
    "else:",
    "    raise AssertionError('Check subprocess has network access')",
  ].join("\n");
  const command = [
    "import subprocess, sys",
    "from pathlib import Path",
    networkCheck,
    `subprocess.run([sys.executable, '-c', ${JSON.stringify(networkCheck)}], check=True)`,
    "assert '    return 42' in Path('src/app.py').read_text(), 'Expected 42'",
  ].join("\n");
  return api<SaveDraftResult>(request, "PATCH", path, {
    checks: [{
      key: "V1", owner: "P1.1", kind: "command", category: "acceptance", required: true,
      definition: { argv: ["/usr/bin/python3", "-c", command], cwd: { mount: "main", path: "." } },
    }],
  }, {
    headers: { "If-Match": `W/"v${version}"`, "Content-Type": "application/merge-patch+json" },
  });
}

async function publishRunPlan(page: Page, request: APIRequestContext) {
  const title = "Synthetic code correction";
  const goal = "Deliver a checked, approved answer";
  const project = projectId();
  await signIn(page, undefined, `/p/${project}/plans`);
  await page.getByRole("button", { name: "Создать план", exact: true }).click();
  const create = page.getByRole("dialog", { name: "Создать план" });
  await create.getByRole("textbox", { name: "Название плана" }).fill(title);
  await create.getByRole("combobox", { name: "Шаблон" }).selectOption("feature");
  await create.getByRole("textbox", { name: "title", exact: true }).fill(title);
  await create.getByRole("textbox", { name: "goal", exact: true }).fill(goal);
  const created = responseFor(page, "POST", `/api/v1/projects/${project}/plans`);
  await create.getByRole("button", { name: "Создать", exact: true }).click();
  const creation = await created;
  expect(creation.status(), await creation.text()).toBe(201);
  expect(creation.request().postDataJSON()).toMatchObject({ template_key: "feature" });
  const { plan_id, draft_id, edit_version } = await creation.json() as CreatePlanResult;
  if (draft_id === null || edit_version === null) throw new Error("The feature template did not create a draft");
  const draftPath = `/plans/${plan_id}/drafts/${draft_id}`;
  await expect(page).toHaveURL(new RegExp(`${draftPath}$`));

  // Adding a check defaults to manual. Changing its kind retains manual-only definition fields.
  const prepared = await seedCommandCheck(request, draftPath, edit_version);
  await page.reload();

  const editor = page.getByRole("region", { name: "Поля сущности" });
  const findings = page.getByRole("region", { name: "Findings" });
  const skeleton = findings.getByRole("button", { name: /^phase_skeleton · P1 / });
  const missingScope = findings.getByRole("button", { name: /^write_scope_empty · P1\.1 / });
  await skeleton.click();
  await editor.getByRole("radio", { name: "detailed", exact: true }).check();

  await missingScope.click();
  const itemTitle = editor.getByRole("textbox", { name: "title", exact: true });
  await expect(itemTitle).toHaveValue(title);
  await itemTitle.fill("Return 42");
  const scope = editor.getByRole("group", { name: "scope", exact: true });
  await fillArray(scope.getByRole("group", { name: /^include/ }), ["main:src/**"]);
  await fillArray(scope.getByRole("group", { name: /^exclude/ }), ["main:README.md"]);
  await fillArray(editor.getByRole("group", { name: "deliverables", exact: true }), ["An integrated function with a passing check"]);
  const hints = editor.getByRole("group", { name: "change_hints", exact: true });
  await hints.getByRole("button", { name: "Добавить элемент", exact: true }).click();
  await hints.getByRole("textbox", { name: "mount", exact: true }).fill("main");
  await hints.getByRole("textbox", { name: "pattern", exact: true }).fill("src/app.py");
  await hints.getByRole("radio", { name: "any", exact: true }).check();
  const review = editor.getByRole("group", { name: /^review/ });
  await review.getByRole("combobox", { name: "mode", exact: true }).selectOption({ label: "self" });
  await review.getByRole("textbox", { name: "reason", exact: true }).fill("Synthetic test");

  await page.getByRole("button", { name: "+ Check", exact: true }).click();
  await expect(editor.getByRole("textbox", { name: "key", exact: true })).toHaveValue("V2");
  await editor.getByRole("textbox", { name: "instructions_md", exact: true }).fill("Confirm the synthetic answer");
  await editor.getByRole("radio", { name: "owner", exact: true }).check();

  const saved = responseFor(page, "PATCH", `/api/v1${draftPath}`);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const saveResponse = await saved;
  expect(saveResponse.ok(), await saveResponse.text()).toBe(true);
  expect(saveResponse.request().headers()["if-match"]).toBe(`W/"v${prepared.edit_version}"`);
  const savedDraft = await saveResponse.json() as SaveDraftResult;
  await expect(skeleton).toHaveCount(0);
  await expect(missingScope).toHaveCount(0);
  await expect(findings).toBeVisible();

  const previewed = responseFor(page, "POST", `/api/v1${draftPath}/publication-preview`);
  await page.getByRole("button", { name: "Publish…", exact: true }).click();
  const previewResponse = await previewed;
  expect(previewResponse.ok(), await previewResponse.text()).toBe(true);
  expect(previewResponse.request().postDataJSON()).toMatchObject({ expected_edit_version: savedDraft.edit_version });
  const preview = await previewResponse.json() as PublicationPreviewView;
  expect(preview.publishable, JSON.stringify(preview.validation)).toBe(true);

  const publication = page.getByRole("dialog", { name: "Публикация черновика" });
  await publication.getByRole("textbox", { name: "Причина публикации" }).fill("Publish the M5 acceptance plan");
  const published = responseFor(page, "POST", `/api/v1${draftPath}/publish`);
  await publication.getByRole("button", { name: "Publish shown changes" }).click();
  const publishResponse = await published;
  expect(publishResponse.status(), await publishResponse.text()).toBe(201);
  expect(publishResponse.request().postDataJSON()).toMatchObject({ expected_content_digest: preview.content_digest });
  const revision = await publishResponse.json() as PublishRevisionResult;
  await publication.getByRole("link", { name: `ревизия r${revision.revision_no}` }).click();
  await expect(page).toHaveURL(new RegExp(`/plans/${plan_id}/revisions/${revision.revision_id}(?:\\?|$)`));
  return revision;
}

test("publishes a template plan and runs its revision through rework, a question and a manual check", async ({ page, request, context }) => {
  test.setTimeout(90_000);
  const revision = await test.step("Create, edit and publish the template plan", () => publishRunPlan(page, request));
  await page.getByRole("button", { name: "Запустить", exact: true }).click();
  const start = page.getByRole("dialog", { name: "Новый запуск" });
  await start.getByRole("textbox", { name: "Ключи задач через запятую" }).fill("P1.1");
  const planPath = `/api/v1/plans/${revision.plan_id}`;
  const verified = responseFor(page, "POST", `${planPath}/revisions/${revision.revision_id}/readiness`);
  await start.getByRole("button", { name: "Проверить готовность" }).click();
  const readiness = await (await verified).json() as ValidateForExecutionResult;
  expect(readiness.status, JSON.stringify(readiness.findings)).toMatch(/^ready/);
  await start.getByRole("textbox", { name: "Причина" }).fill("Exercise M5 operator flow");
  const started = responseFor(page, "POST", `${planPath}/runs`);
  await start.getByRole("button", { name: "Запустить", exact: true }).click();
  const response = await started;
  expect(response.status(), await response.text()).toBe(201);
  expect(response.request().postDataJSON()).toMatchObject({ revision_id: revision.revision_id });
  const { run_id } = await response.json() as StartRunResult;
  await expect(page).toHaveURL(new RegExp(`/runs/${run_id}`));

  const graph = page.getByRole("list", { name: "Зависимости задач" });
  await expect(graph).toBeVisible();
  const task = graph.getByText("P1.1", { exact: true });
  await task.click();
  const attempt = page.getByRole("link", { name: "Попытка 1", exact: true });
  await expect(attempt).toBeVisible({ timeout: 14_000 });
  await attempt.click();
  const live = page.getByRole("region", { name: "Прямой эфир попытки" });
  await expect(live.getByText("First synthetic implementation", { exact: false })).toBeVisible({ timeout: 15_000 });

  const inbox = await context.newPage();
  await signIn(inbox, undefined, `/inbox?project_id=${projectId()}`);
  const question = inbox.getByRole("article").filter({ hasText: "Which synthetic behavior should be implemented?" });
  await expect(question).toBeVisible({ timeout: 25_000 });
  await question.getByRole("textbox", { name: "Текст ответа" }).fill("Return 42");
  await question.getByRole("textbox", { name: "Обоснование" }).fill("Use the expected test value");
  const answered = responseFor(inbox, "POST", /\/decision-requests\/[^/]+\/answer$/);
  await question.getByRole("button", { name: "Ответить", exact: true }).click();
  const answer = await answered;
  expect(answer.ok(), await answer.text()).toBe(true);

  const manual = inbox.getByRole("article", { name: /P1\.1:V2/ });
  await expect(manual).toBeVisible({ timeout: 20_000 });
  await manual.getByRole("textbox", { name: "Комментарий" }).fill("Checked the synthetic result");
  const recorded = responseFor(inbox, "POST", /\/check-executions\/[^/]+\/verdict$/);
  await manual.getByRole("button", { name: "Пройдена", exact: true }).click();
  const verdict = await recorded;
  expect(verdict.ok(), await verdict.text()).toBe(true);

  await page.goto(`/runs/${run_id}?project_id=${projectId()}`);
  await expect(page.getByRole("heading", { name: new RegExp(`r${revision.revision_no}.*succeeded`) })).toBeVisible({ timeout: 20_000 });
  const history = await api<HistoryPage>(request, "GET", `/runs/${run_id}/history?limit=200`);
  expect(history.entries.map((entry) => entry.event_type)).toContain("urn:skm:execution:event:task-rework-required:v1");
  await page.getByRole("tab", { name: "Бюджет" }).click();
  await expect(page.getByRole("heading", { name: "Бюджет", exact: true })).toBeVisible();
});
