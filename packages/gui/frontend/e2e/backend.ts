import { execFileSync, spawn } from "node:child_process";
import { cpSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const gui = resolve(here, "..", "..");
const fixtures = join(gui, "tests", "fixtures", "units", "e2e");
// The planner bridge and the hub command line it calls are the hub's own; the plan is a copy of a fixture, in the
// throwaway project, so no real plan is ever read or written.
const hub = resolve(gui, "..", "..");
const bridge = join(hub, "bridges", "gui-planner");
const umbrella = join(hub, "bin", "swissknifeman");
// SKM_UNITS_PATH replaces the hub registry for the backend and for every plugin it starts (the environment of a
// plugin passes it on), so the umbrella the bridge calls can find the planner only if the planner is on the path too;
// the bridge finds the model catalog of the foundation through AICORE_ROOT, which also reaches the plugin.
const planner = join(hub, "packages", "planner");
// The workspace bridge and the workspace module it calls (workspace.spec.ts); the workspace root is throwaway too.
const workspaceBridge = join(hub, "bridges", "gui-workspace");
const workspaceModule = join(hub, "packages", "workspace");
const foundation = join(hub, "packages", "aicore");
const planFixture = join(gui, "tests", "fixtures", "plans", "e2e");
// The sample external extension lives outside tests/fixtures/units on purpose: it is not a hub unit, so it is never
// on SKM_UNITS_PATH. It reaches the backend only through [aicore.plugins.ext-demo] of the machine layer of the
// throwaway home (an absolute manifest path, enabled and trusted for aicore); the GUI still needs an explicit Enable.
const extension = join(gui, "tests", "fixtures", "extensions", "ext-demo");

/** Global setup: one `gui serve` for every spec, on a free port, in a throwaway home; returns the teardown. */
export default async function setup(): Promise<() => Promise<void>> {
  const pydeps = execFileSync(join(gui, "bin", "gui"), ["deps", "path"], { encoding: "utf8" }).trim();
  const base = mkdtempSync(join(tmpdir(), "gui-e2e-"));
  const project = join(base, "project");
  mkdirSync(join(project, ".git"), { recursive: true });
  mkdirSync(join(base, "home"));
  cpSync(planFixture, join(project, "plans"), { recursive: true });
  mkdirSync(join(base, "skm", "config"), { recursive: true });
  const configFile = join(base, "skm", "config", "config.toml");
  const config = [
    "schema_version = 1",
    "",
    "[gui.plugins]",
    "drain_timeout_s = 2",
    "",
    "[gui.runs]",
    "cancel_grace_s = 2",
    "",
    "[aicore.plugins.ext-demo]",
    `manifest = ${JSON.stringify(join(extension, "extension.json"))}`,
    "enabled = true",
    "trusted = true",
    "",
    "[aicore.plugins.workspace-planner]",
    `manifest = ${JSON.stringify(join(hub, "bridges", "workspace-planner", "extension.json"))}`,
    "enabled = true",
    "trusted = true",
    "",
  ].join("\n");
  writeFileSync(configFile, config);
  const env = {
    PATH: process.env.PATH ?? "/usr/bin:/bin",
    HOME: join(base, "home"),
    SKM_HOME: join(base, "skm"),
    SKM_UNITS_PATH: [fixtures, bridge, planner, workspaceBridge, workspaceModule].join(delimiter),
    SKM_WORKSPACES_ROOT: join(base, "workspaces"),
    SKM_WORKSPACE: "axioma",
    SKM_WORKSPACE_MODULE_ROOT: workspaceModule,
    GIT_CONFIG_GLOBAL: "/dev/null",
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_AUTHOR_NAME: "e2e",
    GIT_AUTHOR_EMAIL: "e2e@example.invalid",
    GIT_COMMITTER_NAME: "e2e",
    GIT_COMMITTER_EMAIL: "e2e@example.invalid",
    AICORE_ROOT: foundation,
    SKM_UMBRELLA: umbrella,
    GUI_PYDEPS_DIR: pydeps,
    LANG: "C.UTF-8",
  };
  const child = spawn(join(gui, "bin", "gui"), ["serve", "--port", "0", "--no-browser", "--project", project], {
    env, stdio: ["ignore", "pipe", "pipe"],
  });
  let stderr = "";
  child.stderr.on("data", (data: Buffer) => (stderr += data.toString()));
  const url = await new Promise<string>((done, fail) => {
    const timer = setTimeout(() => fail(new Error(`gui serve did not print GUI_URL in 30 s:\n${stderr}`)), 30_000);
    createInterface({ input: child.stdout }).on("line", (line) => {
      if (line.startsWith("GUI_URL ")) {
        clearTimeout(timer);
        done(line.slice("GUI_URL ".length).trim());
      }
    });
    child.on("exit", (code) => fail(new Error(`gui serve exited with ${code}:\n${stderr}`)));
  });
  const runtime = JSON.parse(readFileSync(join(base, "skm", "state", "gui", "backend.json"), "utf8"));
  process.env.GUI_E2E_URL = url;
  process.env.GUI_E2E_ORIGIN = new URL(url).origin;
  process.env.GUI_E2E_SECRET = runtime.session_secret;
  process.env.GUI_E2E_PROJECT = project;
  process.env.GUI_E2E_UMBRELLA = umbrella;
  process.env.GUI_E2E_HOME = join(base, "home");
  process.env.GUI_E2E_BASE = base;
  process.env.GUI_E2E_SKM_HOME = join(base, "skm");
  process.env.GUI_E2E_WORKSPACE = join(base, "workspaces", "axioma");
  process.env.GUI_E2E_WORKSPACE_MODULE = workspaceModule;
  // config.spec.ts rewrites the machine layer; plugins.spec.ts puts this text back before it needs the extension
  process.env.GUI_E2E_CONFIG_FILE = configFile;
  process.env.GUI_E2E_CONFIG_TEXT = config;
  return async () => {
    child.kill("SIGTERM");
    await new Promise((done) => {
      const timer = setTimeout(() => {
        child.kill("SIGKILL");
        done(null);
      }, 15_000);
      child.on("exit", () => {
        clearTimeout(timer);
        done(null);
      });
    });
    rmSync(base, { recursive: true, force: true });
  };
}
