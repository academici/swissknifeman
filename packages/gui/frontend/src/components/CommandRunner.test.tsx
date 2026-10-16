import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Command } from "../contracts";
import { ApiError } from "../transport/ApiError";
import { FakeTransport, Wrapper, type Call } from "../test/fakes";
import { CommandRunner } from "./CommandRunner";

const COMMAND: Command = {
  owner: "xdemo", id: "xdemo.echo", title: "Echo", scope: "project", effects: ["process.spawn"], risk: "medium",
  confirmation: "risk-based", supports: ["dry-run", "cancel", "stream"], timeout_s: 30, exec_kind: "argv",
  input: [
    { name: "name", title: "Name", type: "string", required: true },
    { name: "count", title: "Count", type: "integer", required: false, flag: "--count" },
    { name: "loud", title: "Loud", type: "boolean", required: false, flag: "--loud" },
  ],
};
const RUN = { run_id: `run-${"b".repeat(32)}` };

function setup(answer: (call: Call) => unknown) {
  const transport = new FakeTransport({
    "GET /v1/commands": { $schema: "urn:swissknifeman:gui:run-api:v1", kind: "command_list", commands: [COMMAND] },
    "POST /v1/commands/xdemo.echo/runs": answer,
  });
  render(
    <Wrapper transport={transport}>
      <CommandRunner commandId="xdemo.echo" projectId="proj-1a2b3c4d" />
    </Wrapper>,
  );
  return transport;
}

describe("command form", () => {
  it("sends only the typed run request, then confirms on 428", async () => {
    let attempts = 0;
    const transport = setup(() => {
      attempts += 1;
      return attempts === 1
        ? new ApiError(428, { code: "CONFIRMATION_REQUIRED", message: "confirm", details: { confirm: "f".repeat(64), risk: "medium", summary: "Run Echo" } })
        : RUN;
    });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Name *"), "World");
    await user.type(screen.getByLabelText("Count"), "3");
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.getByText(/Run Echo/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Confirm and run" }));
    await waitFor(() => expect(attempts).toBe(2));
    const posts = transport.calls.filter((call) => call.method === "POST").map((call) => call.body as Record<string, unknown>);
    expect(posts[0]).toEqual({ $schema: "urn:swissknifeman:gui:run-api:v1", kind: "run_request",
      context: { project_id: "proj-1a2b3c4d" }, input: { name: "World", count: 3, loud: false }, dry_run: false });
    expect(posts[1]).toEqual({ ...posts[0], confirm: "f".repeat(64) });
    for (const body of posts) expect(Object.keys(body).sort()).not.toContain("argv");
  });

  it("dry run sends dry_run true", async () => {
    const transport = setup(() => RUN);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Name *"), "x");
    await user.click(screen.getByRole("button", { name: "Dry run" }));
    await waitFor(() => expect(transport.calls.some((call) => call.method === "POST")).toBe(true));
    const post = transport.calls.find((call) => call.method === "POST")!.body as Record<string, unknown>;
    expect(post.dry_run).toBe(true);
  });

  it("shows the issues of INPUT_INVALID", async () => {
    setup(() => new ApiError(422, { code: "INPUT_INVALID", message: "1 invalid value(s)",
      issues: [{ pointer: "/input/name", code: "leading_dash", message: "must not start with '-'" }] }));
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Name *"), "-rf");
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByText("INPUT_INVALID")).toBeTruthy();
    expect(screen.getByText(/leading_dash/)).toBeTruthy();
  });
});
