import { execFileSync, spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const gui = resolve(here, "..", "..");
const fixtures = join(gui, "tests", "fixtures", "units", "e2e");

/** Global setup: one `gui serve` for every spec, on a free port, in a throwaway home; returns the teardown. */
export default async function setup(): Promise<() => Promise<void>> {
  const pydeps = execFileSync(join(gui, "bin", "gui"), ["deps", "path"], { encoding: "utf8" }).trim();
  const base = mkdtempSync(join(tmpdir(), "gui-e2e-"));
  const project = join(base, "project");
  mkdirSync(join(project, ".git"), { recursive: true });
  mkdirSync(join(base, "home"));
  const env = {
    PATH: process.env.PATH ?? "/usr/bin:/bin",
    HOME: join(base, "home"),
    SKM_HOME: join(base, "skm"),
    SKM_UNITS_PATH: fixtures,
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
