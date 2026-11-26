import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ViewData } from "./contracts";
import { App } from "./app/App";
import { REQUIRED_CONTRACTS } from "./app/compat";
import type { Draft } from "./forms/draft";
import { PreviewDialog } from "./forms/PreviewDialog";
import { GrantDialog } from "./plugins/GrantDialog";
import { Projects } from "./pages/Projects";
import { FakeTransport, Wrapper } from "./test/fakes";
import { trust } from "./test/plugins";
import { ApiError } from "./transport/ApiError";

vi.mock("./terminal/TerminalView", () => ({ TerminalView: () => <div>terminal view</div> }));

const examples = import.meta.glob("../../schemas/view-data/v1/examples/valid/*.json", { eager: true, import: "default" });
const STATUS_TABLE = examples["../../schemas/view-data/v1/examples/valid/status-table.json"] as ViewData;

const bootstrap = {
  $schema: "urn:swissknifeman:gui:bootstrap:v1",
  mode: "browser",
  epoch: "epoch-0001",
  backend: { version: "0.1.0", python: "3.12.3" },
  gui_protocol: { min: "1", max: "1" },
  contracts: REQUIRED_CONTRACTS.map(([id, version]) => ({ id, version })),
  units: [],
  features: ["queries", "projects", "runs", "events", "config", "plugins", "terminal"],
  platform: { os: "linux", arch: "x86_64" },
};
const catalog = {
  $schema: "urn:swissknifeman:gui:catalog:v1",
  host: { gui_protocol: { min: "1", max: "1" } },
  contributions: [
    {
      owner: "demo",
      source: "unit",
      file: "/units/demo/gui.json",
      digest: `sha256:${"2".repeat(64)}`,
      document: {
        routes: [{ id: "demo.page", title: "Demo page", path: "page", view: "status-table", scope: "fleet", nav: { section: "fleet", order: 1 } }],
        widgets: [{ id: "demo.widget", title: "Demo status", query: "demo.status", scope: "fleet", size: "medium" }],
      },
    },
  ],
  rejected: [{ owner: "bad", file: "/units/bad/gui.json", code: "CONTRIB_INVALID", message: "no routes" }],
  digest: `sha256:${"0".repeat(64)}`,
};
const project = { id: "proj-0a1b2c3d", name: "proj", root: "/p", trusted: true, source: "open", added_at: "2026-10-17T10:00:00Z" };
const projects = { $schema: "urn:swissknifeman:gui:project:v1", kind: "project_list", projects: [project] };
const runs = {
  $schema: "urn:swissknifeman:gui:run-api:v1",
  kind: "run_list",
  runs: [{ run_id: `run-${"a".repeat(32)}`, command: "demo.build", dry_run: false, state: "succeeded", created_at: "2026-10-17T10:00:00Z" }],
};

function backend() {
  return new FakeTransport({
    "GET /v1/bootstrap": bootstrap,
    "GET /v1/ui/contributions": catalog,
    "POST /v1/queries/demo.status": STATUS_TABLE,
    "GET /v1/projects": projects,
    "GET /v1/runs?limit=100": runs,
    "GET /v1/config": { modules: [{ id: "gui", title: "GUI settings" }] },
    "GET /v1/plugins": { $schema: "urn:swissknifeman:gui:plugin-api:v1", kind: "plugin_list", plugins: [trust("hub-bridge", { source: "unit" })] },
    "GET /v1/terminal/sessions": { $schema: "urn:swissknifeman:gui:terminal:v1", kind: "session_list", sessions: [] },
    "GET /v1/commands": { $schema: "urn:swissknifeman:gui:run-api:v1", kind: "command_list", commands: [] },
  });
}

/** The accessible name of a control: aria-label, aria-labelledby, its label elements, its value (buttons), its text, title. */
function accessibleName(element: Element): string {
  const label = element.getAttribute("aria-label")?.trim();
  if (label) return label;
  const by = element.getAttribute("aria-labelledby");
  if (by) {
    const text = by
      .split(/\s+/)
      .map((id) => element.ownerDocument.getElementById(id)?.textContent ?? "")
      .join(" ")
      .trim();
    if (text) return text;
  }
  if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
    const labels = Array.from(element.labels ?? [])
      .map((entry) => entry.textContent ?? "")
      .join(" ")
      .trim();
    if (labels) return labels;
    if (element instanceof HTMLInputElement && ["button", "submit", "reset"].includes(element.type) && element.value) return element.value;
    return element.getAttribute("title")?.trim() ?? "";
  }
  return (element.textContent ?? "").trim() || element.getAttribute("title")?.trim() || "";
}

/** What a screen must satisfy: unique ids, named controls, one h1, no skipped heading level, labelled landmarks. */
function audit(root: HTMLElement): string[] {
  const problems: string[] = [];
  const ids = Array.from(root.querySelectorAll("[id]")).map((element) => element.id);
  for (const id of new Set(ids.filter((id, index) => ids.indexOf(id) !== index))) problems.push(`duplicate id ${id}`);

  const controls = root.querySelectorAll("button, a[href], input:not([type=hidden]), select, textarea, [role=button], [role=link]");
  for (const control of Array.from(controls)) {
    if (accessibleName(control) === "") problems.push(`no accessible name: <${control.tagName.toLowerCase()} class="${control.className}">`);
  }

  const headings = Array.from(root.querySelectorAll("h1, h2, h3, h4, h5, h6"));
  const levels = headings.map((heading) => Number(heading.tagName.slice(1)));
  if (levels.filter((level) => level === 1).length !== 1) problems.push(`expected exactly one h1, found ${levels.filter((level) => level === 1).length}`);
  levels.forEach((level, index) => {
    if (index > 0 && level > (levels[index - 1] ?? 0) + 1) problems.push(`heading level jumps from h${levels[index - 1]} to h${level}`);
    if (accessibleName(headings[index]!) === "") problems.push(`empty h${level}`);
  });

  for (const nav of Array.from(root.querySelectorAll("nav"))) {
    if (!nav.getAttribute("aria-label")) problems.push("a nav landmark without aria-label");
  }
  for (const dialog of Array.from(root.querySelectorAll("[role=dialog]"))) {
    if (!dialog.getAttribute("aria-label") && !dialog.getAttribute("aria-labelledby")) problems.push("a dialog without a name");
  }
  return problems;
}

const SCREENS: Array<{ name: string; path: string; heading: string; ready: () => Promise<unknown> }> = [
  { name: "Dashboard", path: "/", heading: "Fleet", ready: () => screen.findByRole("heading", { level: 2, name: "Demo status" }) },
  { name: "Projects", path: "/projects", heading: "Projects", ready: () => screen.findByRole("link", { name: "proj" }) },
  { name: "Runs", path: "/runs", heading: "Runs", ready: () => screen.findByRole("link", { name: /^run-a/ }) },
  { name: "Catalog", path: "/catalog", heading: "Catalog", ready: () => screen.findByRole("cell", { name: "demo" }) },
  { name: "Plugins", path: "/plugins", heading: "Plugins", ready: () => screen.findByRole("link", { name: "hub-bridge" }) },
  { name: "Configuration", path: "/settings/config", heading: "Configuration", ready: () => screen.findByRole("link", { name: "gui" }) },
  { name: "Terminal", path: "/terminal", heading: "Terminal", ready: () => screen.findByRole("button", { name: "Open terminal" }) },
];

describe("accessibility of the real screens (App with a FakeTransport)", () => {
  for (const screenCase of SCREENS) {
    it(`${screenCase.name}: names, one h1, heading order, labelled landmarks`, async () => {
      const { container } = render(
        <Wrapper transport={backend()} path={screenCase.path}>
          <App />
        </Wrapper>,
      );
      await screen.findByRole("heading", { level: 1, name: screenCase.heading });
      await screenCase.ready();
      await waitFor(() => expect(screen.queryByText(/^Loading/)).toBeNull());
      expect(audit(container)).toEqual([]);
      const current = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link").filter((link) => link.getAttribute("aria-current") === "page");
      expect(current.map((link) => link.textContent)).toEqual([screenCase.name]);
    });
  }

  it("the audit itself catches an unnamed button, a duplicate id and a skipped heading", () => {
    const { container } = render(
      <div>
        <h1>One</h1>
        <h3>Skipped</h3>
        <button type="button" />
        <span id="x" />
        <span id="x" />
        <nav />
      </div>,
    );
    expect(audit(container)).toEqual([
      "duplicate id x",
      'no accessible name: <button class="">',
      "heading level jumps from h1 to h3",
      "a nav landmark without aria-label",
    ]);
  });

  it("Tab reaches the navigation first, and the current page is marked", async () => {
    render(
      <Wrapper transport={backend()} path="/projects">
        <App />
      </Wrapper>,
    );
    await screen.findByRole("heading", { level: 1, name: "Projects" });
    await userEvent.setup().tab();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(document.activeElement).toBe(within(nav).getByRole("link", { name: "Dashboard" }));
    expect(within(nav).getByRole("link", { name: "Projects" }).getAttribute("aria-current")).toBe("page");
    expect(within(nav).getByRole("link", { name: "Runs" }).getAttribute("aria-current")).toBeNull();
  });

  it("every nav link is reachable by Tab in document order", async () => {
    render(
      <Wrapper transport={backend()} path="/">
        <App />
      </Wrapper>,
    );
    await screen.findByRole("heading", { level: 2, name: "Demo status" });
    const nav = screen.getByRole("navigation", { name: "Main" });
    const links = within(nav).getAllByRole("link");
    const user = userEvent.setup();
    const reached: Element[] = [];
    for (let index = 0; index < links.length; index += 1) {
      await user.tab();
      reached.push(document.activeElement!);
    }
    expect(reached).toEqual(links);
  });
});

describe("dialogs take the focus and give it back", () => {
  it("project confirmation: focus moves into the dialog and Cancel returns it to Add", async () => {
    const user = userEvent.setup();
    const fake = new FakeTransport({
      "GET /v1/projects": { $schema: "urn:swissknifeman:gui:project:v1", kind: "project_list", projects: [] },
      "POST /v1/projects": new ApiError(428, {
        code: "CONFIRMATION_REQUIRED",
        message: "confirm",
        details: { confirm: "c".repeat(64), summary: "Trust /p?", risk: "medium" },
      }),
    });
    render(
      <Wrapper transport={fake}>
        <Projects />
      </Wrapper>,
    );
    await user.type(await screen.findByLabelText("Add a project (absolute folder path)"), "/p");
    const add = screen.getByRole("button", { name: "Add" });
    await user.click(add);
    const dialog = await screen.findByRole("dialog", { name: "Confirm the project" });
    expect(document.activeElement).toBe(dialog);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(add);
  });

  it("project confirmation: Escape closes the dialog and returns the focus", async () => {
    const user = userEvent.setup();
    const fake = new FakeTransport({
      "GET /v1/projects": { $schema: "urn:swissknifeman:gui:project:v1", kind: "project_list", projects: [] },
      "POST /v1/projects": new ApiError(428, { code: "CONFIRMATION_REQUIRED", message: "confirm", details: { confirm: "c".repeat(64), summary: "Trust /p?" } }),
    });
    render(
      <Wrapper transport={fake}>
        <Projects />
      </Wrapper>,
    );
    await user.type(await screen.findByLabelText("Add a project (absolute folder path)"), "/p");
    const add = screen.getByRole("button", { name: "Add" });
    await user.click(add);
    await screen.findByRole("dialog", { name: "Confirm the project" });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(add);
  });

  function GrantHarness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Open grant
        </button>
        {open && <GrantDialog plugin={trust("ext-demo")} onClose={() => setOpen(false)} />}
      </>
    );
  }

  it("grant dialog: focus in, Close and Escape return it to the opener", async () => {
    const user = userEvent.setup();
    const fake = new FakeTransport({ "GET /v1/projects": projects });
    render(
      <Wrapper transport={fake}>
        <GrantHarness />
      </Wrapper>,
    );
    const opener = screen.getByRole("button", { name: "Open grant" });
    await user.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Grant for ext-demo" });
    expect(document.activeElement).toBe(dialog);
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);

    await user.click(opener);
    expect(document.activeElement).toBe(screen.getByRole("dialog", { name: "Grant for ext-demo" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  const DRAFT: Draft = { module: "gui", layer: "machine", revision: "r1", base: {}, ops: new Map() };
  const PREVIEW = {
    $schema: "urn:swissknifeman:gui:config-mutation:v1",
    kind: "preview",
    preview_id: "p".repeat(64),
    file: "/home/me/.skm/gui.toml",
    diff: [],
    issues: [],
    confirm_required: false,
    confirm_reasons: [],
  };

  function PreviewHarness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Open preview
        </button>
        {open && <PreviewDialog draft={DRAFT} projectId={null} onApplied={() => setOpen(false)} onConflict={() => setOpen(false)} onClose={() => setOpen(false)} />}
      </>
    );
  }

  it("preview dialog: focus in, Close returns it to the opener", async () => {
    const user = userEvent.setup();
    const fake = new FakeTransport({ "POST /v1/config/gui/preview": PREVIEW });
    render(
      <Wrapper transport={fake}>
        <PreviewHarness />
      </Wrapper>,
    );
    const opener = screen.getByRole("button", { name: "Open preview" });
    await user.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Preview of the change" });
    expect(document.activeElement).toBe(dialog);
    await screen.findByRole("button", { name: "Apply" });
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
});
