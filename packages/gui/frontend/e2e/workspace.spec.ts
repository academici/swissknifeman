import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { api, origin, signIn } from "./session";

// The workspace of these scenarios is the throwaway one of the backend (workspace axioma under SKM_WORKSPACES_ROOT); machine B is a second
// SKM_HOME and workspaces folder next to it. The command line of the workspace module is what the bridge calls too.
const base = () => process.env.GUI_E2E_BASE ?? "";
const module = () => process.env.GUI_E2E_WORKSPACE_MODULE ?? "";
const remoteDir = () => join(base(), "remote.git");
const remoteUrl = () => `file://${remoteDir()}`;
const appDir = () => join(base(), "app");
const workspacesRoot = () => dirname(process.env.GUI_E2E_WORKSPACE ?? "");

type Machine = "a" | "b";

function env(machine: Machine): NodeJS.ProcessEnv {
  const home = machine === "a" ? process.env.GUI_E2E_HOME : join(base(), "home-b");
  return {
    PATH: process.env.PATH ?? "/usr/bin:/bin", HOME: home, LANG: "C.UTF-8",
    SKM_HOME: machine === "a" ? process.env.GUI_E2E_SKM_HOME : join(base(), "skm-b"),
    SKM_WORKSPACES_ROOT: machine === "a" ? dirname(process.env.GUI_E2E_WORKSPACE ?? "") : join(base(), "workspaces-b"),
    SKM_WORKSPACE: "axioma",
    AICORE_ROOT: join(module(), "..", "aicore"),
    GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1",
    GIT_AUTHOR_NAME: "e2e", GIT_AUTHOR_EMAIL: "e2e@example.invalid", GIT_COMMITTER_NAME: "e2e", GIT_COMMITTER_EMAIL: "e2e@example.invalid",
  };
}

function ws(machine: Machine, ...args: string[]): string {
  return execFileSync(join(module(), "bin", "workspace"), args, { env: env(machine), encoding: "utf8", cwd: base() });
}

function git(cwd: string, ...args: string[]): string {
  return execFileSync("git", args, { cwd, env: env("a"), encoding: "utf8" });
}

function workspaceStatus(): { projects: Array<{ project_id: string }> } {
  return JSON.parse(ws("a", "status", "--json")) as { projects: Array<{ project_id: string }> };
}

function projectPaths(code: string): string[] {
  const listed = JSON.parse(ws("a", "project", "list", "--json")) as { projects: Array<{ project_id: string; paths: string[] }> };
  return listed.projects.find((entry) => entry.project_id === code)?.paths ?? [];
}

/** Opens a page of the bridge and one of its actions (the actions sit in a details element named by the command id). */
async function openAction(page: Page, path: string, command: string) {
  await page.goto(`${origin()}/x/gui-workspace/${path}`);
  // the whole text: gui-workspace.init is also the start of gui-workspace.init-remote
  const details = page.locator("details", { has: page.locator("summary", { hasText: new RegExp(`^${command.replace(/\./g, "\\.")}$`) }) });
  await details.locator("summary").click();
  return details;
}

/** Runs the form of an action; confirms when the host asks; waits for the run page and its final state. */
async function runForm(page: Page, form: ReturnType<Page["locator"]>, confirm = false, final: "succeeded" | "failed" = "succeeded"): Promise<void> {
  await form.getByRole("button", { name: "Run", exact: true }).click();
  const dialog = page.getByRole("button", { name: "Confirm and run" });
  if (confirm) await expect(dialog).toBeVisible();
  else await expect(dialog.or(page.locator("h1 .status"))).toBeVisible();
  if (await dialog.isVisible()) await dialog.click();
  await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
  await expect(page.locator("h1 .status")).toHaveText(final);
}

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  ws("a", "init", "--code", "axioma");
  mkdirSync(appDir(), { recursive: true });
  git(appDir(), "init", "-q", "-b", "main");
  writeFileSync(join(appDir(), "README.md"), "app\n");
  git(appDir(), "add", "README.md");
  git(appDir(), "commit", "-q", "-m", "chore: base");
  // a legacy plan folder to migrate: a copy of the plans of the throwaway project
  execFileSync("cp", ["-a", join(process.env.GUI_E2E_PROJECT ?? "", "plans"), join(appDir(), "plans")]);
  git(appDir(), "init", "-q", "--bare", "-b", "main", remoteDir());
});

test("the overview of the workspace shows its root state", async ({ page }) => {
  await signIn(page);
  await page.goto(`${origin()}/x/gui-workspace/overview`);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Bound on this machine")).toBeVisible();
  await expect(page.getByText("Publish safety (0 ok, 1 warn, 2 block)")).toBeVisible();
});

test("attach binds a project of this machine and the Projects page offers to trust it, only on confirmation", async ({ page }) => {
  await signIn(page);
  const form = await openAction(page, "projects", "gui-workspace.project-attach");
  await form.getByLabel("Project folder *").fill(appDir());
  await runForm(page, form);
  const id = workspaceStatus().projects[0]?.project_id ?? "";
  expect(id).toBe("app"); // the code of a project is the name of its folder

  // the query answer is cached by the host for a few seconds and the page was read before the attach: reload until it expires
  await expect(async () => {
    await page.goto(`${origin()}/x/gui-workspace/projects`);
    await expect(page.getByRole("cell", { name: "app", exact: true })).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 30_000 });

  // bound but not trusted: no automatic trust, the button asks for a confirmation
  await page.goto(`${origin()}/projects`);
  const trust = page.getByRole("button", { name: `Trust app at ${appDir()}` });
  await expect(trust).toBeVisible();
  expect((await api<{ projects: Array<{ root: string }> }>("/v1/projects")).projects.map((entry) => entry.root)).not.toContain(appDir());
  await trust.click();
  await expect(page.getByRole("dialog", { name: "Confirm the project" })).toBeVisible();
  await page.getByRole("button", { name: "Trust this project" }).click();
  await expect(page.getByRole("button", { name: /^Trust app/ })).toHaveCount(0);
  const binding = page.getByTestId("workspace-binding");
  await expect(binding).toContainText(`project_id ${id}`);
  await expect(binding).toContainText("bound here");
});

test("migrate plan is a dry run of the plans migration and shows its report", async ({ page }) => {
  await signIn(page);
  const form = await openAction(page, "migration", "gui-workspace.migrate-plan");
  await form.getByLabel("Project folder *").fill(appDir());
  await form.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
  await expect(page.locator("h1 .status")).toHaveText(/succeeded|failed/);
  await expect(page.getByTestId("log-stdout")).not.toBeEmpty();
  // the dry run wrote nothing into the workspace
  expect(existsSync(join(process.env.GUI_E2E_WORKSPACE ?? "", "projects", workspaceStatus().projects[0]?.project_id ?? "", "plans"))).toBe(false);
});

test("the connect form binds the workspace to a remote after a confirmation, and a second connect is refused", async ({ page }) => {
  await signIn(page);
  let form = await openAction(page, "overview", "gui-workspace.connect");
  await form.getByLabel("Remote URL *").fill(remoteUrl());
  await runForm(page, form, true);
  expect((JSON.parse(ws("a", "status", "--json")) as { git: { remote: string } }).git.remote).toBe(remoteUrl());

  form = await openAction(page, "overview", "gui-workspace.connect");
  await form.getByLabel("Remote URL *").fill(remoteUrl());
  await runForm(page, form, true, "failed");
  await expect(page.getByTestId("log-stderr")).toContainText("REMOTE_ALREADY_SET");
});

test("push asks for a confirmation after showing the remote and the branch, and publishes the workspace", async ({ page }) => {
  await signIn(page);
  await page.goto(`${origin()}/x/gui-workspace/sync`);
  const target = page.getByRole("row", { name: /Push target/ });
  await expect(target).toContainText(remoteUrl());
  await expect(target).toContainText("branch main");
  await target.getByRole("button", { name: "Repair" }).click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Confirm the run" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm and run" }).click();
  await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
  await expect(page.locator("h1 .status")).toHaveText("succeeded");
  await expect(page.getByTestId("log-stdout")).toContainText(`${remoteUrl()} branch main`);
  expect(git(remoteDir(), "rev-parse", "main").trim()).toBe(git(process.env.GUI_E2E_WORKSPACE ?? "", "rev-parse", "HEAD").trim());
});

test("a sync conflict of the pull is a row of the conflicts table", async ({ page }) => {
  const id = workspaceStatus().projects[0]?.project_id ?? "";
  const rel = join("projects", id, "plans", "CONFLICT", "phases", "P1", "P1.1.json");
  const edit = (machine: Machine, root: string, text: string) => {
    mkdirSync(dirname(join(root, rel)), { recursive: true });
    writeFileSync(join(root, rel), JSON.stringify({ summary: text }) + "\n");
    ws(machine, "sync", "--commit");
  };
  const rootA = process.env.GUI_E2E_WORKSPACE ?? "";
  const rootB = join(base(), "workspaces-b", "axioma");
  mkdirSync(join(base(), "home-b"), { recursive: true });
  edit("a", rootA, "base");
  ws("a", "sync", "--push");
  execFileSync(join(module(), "bin", "workspace"), ["clone", remoteUrl()], { env: env("b"), cwd: base(), encoding: "utf8" });
  edit("b", rootB, "from B");
  ws("b", "sync", "--push");
  edit("a", rootA, "from A");

  await signIn(page);
  await page.goto(`${origin()}/x/gui-workspace/sync`);
  const details = page.locator("details", { has: page.locator("summary", { hasText: "gui-workspace.sync-pull" }) });
  await details.locator("summary").click();
  await details.getByRole("button", { name: "Run", exact: true }).click();
  const confirm = page.getByRole("button", { name: "Confirm and run" });
  await expect(confirm.or(page.locator("h1 .status"))).toBeVisible();
  if (await confirm.isVisible()) await confirm.click();
  await expect(page).toHaveURL(/\/runs\/run-[0-9a-f]{32}$/);
  await expect(page.locator("h1 .status")).toHaveText(/succeeded|failed/);

  await page.goto(`${origin()}/x/gui-workspace/conflicts`);
  const row = page.getByRole("row", { name: new RegExp(rel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
  await expect(row).toBeVisible();
  await expect(row).toContainText(id);
  await expect(row).toContainText("CONFLICT");
});

test("the create form makes a workspace under the workspaces folder and refuses a code that is not one", async ({ page }) => {
  await signIn(page);
  const form = await openAction(page, "overview", "gui-workspace.init");
  await form.getByLabel("Workspace code *").fill("Bad Code");
  await form.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page).toHaveURL(`${origin()}/x/gui-workspace/overview`); // the browser refuses the value: no run starts
  expect(existsSync(join(workspacesRoot(), "Bad Code"))).toBe(false);

  await form.getByLabel("Workspace code *").fill("second");
  await runForm(page, form);
  expect(existsSync(join(workspacesRoot(), "second", "workspace.json"))).toBe(true);
});

test("the create-on-a-remote form binds a new workspace to an empty remote, and refuses a remote that holds a workspace", async ({ page }) => {
  const empty = join(base(), "empty.git");
  git(base(), "init", "-q", "--bare", "-b", "main", empty);
  await signIn(page);
  let form = await openAction(page, "overview", "gui-workspace.init-remote");
  await form.getByLabel("Workspace code *").fill("third");
  await form.getByLabel("Remote URL *").fill(`file://${empty}`);
  await runForm(page, form, true);
  expect(git(join(workspacesRoot(), "third"), "remote", "get-url", "origin").trim()).toBe(`file://${empty}`);

  // remote.git holds the pushed workspace axioma: nothing is created
  form = await openAction(page, "overview", "gui-workspace.init-remote");
  await form.getByLabel("Workspace code *").fill("fourth");
  await form.getByLabel("Remote URL *").fill(remoteUrl());
  await runForm(page, form, true, "failed");
  await expect(page.getByTestId("log-stderr")).toContainText("REMOTE_NOT_EMPTY");
  expect(existsSync(join(workspacesRoot(), "fourth"))).toBe(false);
});

test("the add form adds a checkout as a project with a name and a code, and the rebind form binds another checkout to it", async ({ page }) => {
  const tool = join(base(), "tool");
  mkdirSync(tool, { recursive: true });
  git(tool, "init", "-q", "-b", "main");
  await signIn(page);
  let form = await openAction(page, "projects", "gui-workspace.project-add");
  await form.getByLabel("Project folder *").fill(tool);
  await form.getByLabel("Name", { exact: true }).fill("Tool");
  await form.getByLabel("Project code", { exact: true }).fill("tool-x");
  await runForm(page, form);
  expect(workspaceStatus().projects.map((entry) => entry.project_id)).toContain("tool-x");
  expect(projectPaths("tool-x")).toEqual([tool]);

  // a second checkout of the same project (its marker names the project) replaces the binding
  const copy = join(base(), "tool-copy");
  execFileSync("cp", ["-a", tool, copy]);
  form = await openAction(page, "projects", "gui-workspace.project-rebind");
  await form.getByLabel("Project id *").fill("tool-x");
  await form.getByLabel("Checkout folder *").fill(copy);
  await runForm(page, form);
  expect(projectPaths("tool-x")).toEqual([copy]);
});

test("the remove form removes an empty project after a confirmation and refuses one that holds plans", async ({ page }) => {
  const held = join(process.env.GUI_E2E_WORKSPACE ?? "", "projects", "tool-x", "plans", "KEEP");
  mkdirSync(held, { recursive: true });
  writeFileSync(join(held, "plan.json"), "{}\n");
  await signIn(page);
  let form = await openAction(page, "projects", "gui-workspace.project-remove");
  await form.getByLabel("Project code *").fill("tool-x");
  await runForm(page, form, true, "failed");
  await expect(page.getByTestId("log-stderr")).toContainText("PROJECT_NOT_EMPTY");
  expect(workspaceStatus().projects.map((entry) => entry.project_id)).toContain("tool-x");

  rmSync(held, { recursive: true });
  form = await openAction(page, "projects", "gui-workspace.project-remove");
  await form.getByLabel("Project code *").fill("tool-x");
  await runForm(page, form, true);
  expect(workspaceStatus().projects.map((entry) => entry.project_id)).not.toContain("tool-x");
  expect(existsSync(join(process.env.GUI_E2E_WORKSPACE ?? "", "projects", "tool-x"))).toBe(false);
});
