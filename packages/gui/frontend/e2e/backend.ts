import { execFileSync, spawn } from "node:child_process";
import { cpSync, mkdtempSync, mkdirSync, readFileSync, rmSync } from "node:fs";
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
const foundation = join(hub, "packages", "aicore");
const planFixture = join(gui, "tests", "fixtures", "plans", "e2e");

/** Global setup: one `gui serve` for every spec, on a free port, in a throwaway home; returns the teardown. */
export default async function setup(): Promise<() => Promise<void>> {
  const pydeps = execFileSync(join(gui, "bin", "gui"), ["deps", "path"], { encoding: "utf8" }).trim();
  const base = mkdtempSync(join(tmpdir(), "gui-e2e-"));
  const project = join(base, "project");
  mkdirSync(join(project, ".git"), { recursive: true });
  mkdirSync(join(base, "home"));
  cpSync(planFixture, join(project, "plans"), { recursive: true });
  const env = {
    PATH: process.env.PATH ?? "/usr/bin:/bin",
    HOME: join(base, "home"),
    SKM_HOME: join(base, "skm"),
    SKM_UNITS_PATH: [fixtures, bridge, planner].join(delimiter),
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
