import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../transport/ApiError";
import { FakeTransport, Wrapper } from "../test/fakes";
import { Terminal } from "./Terminal";

const xterm = vi.hoisted(() => ({ loaded: 0 }));
vi.mock("@xterm/xterm", () => {
  xterm.loaded += 1;
  return { Terminal: class {} };
});
vi.mock("../terminal/TerminalView", () => ({
  TerminalView: ({ sessionId }: { sessionId: string }) => <div data-testid="view">{sessionId}</div>,
}));

const bootstrap = (features: string[]) => ({ epoch: "e".repeat(8), features });
const projects = { $schema: "urn:swissknifeman:gui:project:v1", kind: "project_list", projects: [{ id: "proj-0a1b2c3d", name: "proj", root: "/p", trusted: true, source: "open", added_at: "2026-10-17T10:00:00Z" }] };
const session = { $schema: "urn:swissknifeman:gui:terminal:v1", kind: "session", session_id: `term-${"b".repeat(32)}`, project_id: "proj-0a1b2c3d",
  shell: "/bin/sh", cols: 80, rows: 24, started_at: "2026-10-17T10:00:00Z" };
const list = (sessions: unknown[]) => ({ $schema: "urn:swissknifeman:gui:terminal:v1", kind: "session_list", sessions });

describe("Terminal page", () => {
  it("says the terminal is disabled without the feature and does not touch the backend sessions", async () => {
    const fake = new FakeTransport({ "GET /v1/bootstrap": bootstrap(["queries"]) });
    render(<Wrapper transport={fake}><Terminal /></Wrapper>);
    expect((await screen.findByRole("status")).textContent).toContain("Terminal is disabled");
    expect(screen.getByText("[gui.terminal] enabled = true")).toBeTruthy();
    expect(fake.calls.some((call) => call.path.startsWith("/v1/terminal"))).toBe(false);
    expect(xterm.loaded).toBe(0);
  });

  it("asks for the confirmation, shows the summary and starts only after Confirm", async () => {
    let attempts = 0;
    const fake = new FakeTransport({
      "GET /v1/bootstrap": bootstrap(["terminal"]),
      "GET /v1/projects": projects,
      "GET /v1/terminal/sessions": list([]),
      "POST /v1/terminal/sessions": (call: { body: unknown }) => {
        attempts += 1;
        const body = call.body as { confirm?: string; kind: string; project_id: string; cols: number; rows: number };
        expect(body).toMatchObject({ kind: "session_request", project_id: "proj-0a1b2c3d", cols: 80, rows: 24 });
        if (!body.confirm) {
          return new ApiError(428, { code: "CONFIRMATION_REQUIRED", message: "confirm", details: { confirm: "c".repeat(64), risk: "high", summary: "Open a shell (/bin/sh) in /p" } });
        }
        expect(body.confirm).toBe("c".repeat(64));
        return session;
      },
    });
    render(<Wrapper transport={fake}><Terminal /></Wrapper>);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open terminal" }));
    const dialog = await screen.findByRole("dialog", { name: "Open terminal" });
    expect(dialog.textContent).toContain("Open a shell (/bin/sh) in /p");
    expect(screen.queryByTestId("view")).toBeNull();
    expect(attempts).toBe(1);
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect((await screen.findByTestId("view")).textContent).toBe(session.session_id);
    expect(attempts).toBe(2);
  });

  it("a refusal is shown with its code and nothing starts", async () => {
    const fake = new FakeTransport({
      "GET /v1/bootstrap": bootstrap(["terminal"]),
      "GET /v1/projects": projects,
      "GET /v1/terminal/sessions": list([]),
      "POST /v1/terminal/sessions": new ApiError(429, { code: "TERMINAL_LIMIT", message: "at most 2 terminal sessions" }),
    });
    render(<Wrapper transport={fake}><Terminal /></Wrapper>);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Open terminal" }));
    expect((await screen.findByRole("alert")).textContent).toContain("TERMINAL_LIMIT");
    expect(screen.queryByTestId("view")).toBeNull();
  });

  it("lists active sessions, attaches to one and closes another", async () => {
    const other = { ...session, session_id: `term-${"c".repeat(32)}` };
    const entry = (full: typeof session) => ({ session_id: full.session_id, project_id: full.project_id, shell: full.shell,
      cols: full.cols, rows: full.rows, started_at: full.started_at });
    const fake = new FakeTransport({
      "GET /v1/bootstrap": bootstrap(["terminal"]),
      "GET /v1/projects": projects,
      "GET /v1/terminal/sessions": list([entry(session), entry(other)]),
      "POST /v1/terminal/sessions/*": { ...other, ended_at: "2026-10-17T11:00:00Z" },
    });
    render(<Wrapper transport={fake}><Terminal /></Wrapper>);
    const user = userEvent.setup();
    const buttons = await screen.findAllByRole("button", { name: "Close session" });
    expect(buttons).toHaveLength(2);
    await user.click(buttons[1]!);
    await waitFor(() => expect(fake.calls.some((call) => call.path === `/v1/terminal/sessions/${other.session_id}:close`)).toBe(true));
    await user.click(screen.getAllByRole("button", { name: "Attach" })[0]!);
    expect((await screen.findByTestId("view")).textContent).toBe(session.session_id);
  });
});

describe("App loading", () => {
  it("does not load xterm with the app or its pages", async () => {
    const { App } = await import("../app/App");
    const fake = new FakeTransport({
      "GET /v1/bootstrap": {
        $schema: "urn:swissknifeman:gui:bootstrap:v1", mode: "browser", epoch: "e".repeat(8), backend: { version: "0.1.0", python: "3.12.0" },
        gui_protocol: { min: "1", max: "1" }, contracts: [], units: [], features: ["terminal"], platform: { os: "linux", arch: "x86_64" },
      },
      "GET /v1/*": { contributions: [], rejected: [], digest: "d", host: { gui_protocol: { min: "1", max: "1" } }, projects: [], runs: [], kind: "run_list" },
    });
    render(<Wrapper transport={fake}><App /></Wrapper>);
    await waitFor(() => expect(fake.calls.some((call) => call.path === "/v1/bootstrap")).toBe(true));
    expect(xterm.loaded).toBe(0);
  });
});
