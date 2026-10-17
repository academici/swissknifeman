import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "../transport/ApiError";
import { FakeTransport, Wrapper } from "../test/fakes";
import { Projects } from "./Projects";

const TRUSTED = { id: "p1", name: "alpha", root: "/work/alpha" };
const LIST = { $schema: "urn:swissknifeman:gui:project-list:v1", projects: [TRUSTED] };

const row = (id: string, name: string, paths: string, bound = "yes", store = "workspace") => ({
  id, cells: { name, status: "attached", bound, paths, plans_store: store, plans: 1 } });
const WORKSPACE = { $schema: "urn:swissknifeman:gui:view-data:v1", view: "resource-list", columns: [], total: 2,
  rows: [row("prj_aaa", "alpha", "/work/alpha"), row("prj_bbb", "beta", "/work/beta")] };

function open(fake: FakeTransport) {
  return render(<Wrapper transport={fake}><Projects /></Wrapper>);
}

describe("Projects", () => {
  it("shows project_id, binding and plans store of a trusted project and offers Trust for a bound, untrusted one", async () => {
    const fake = new FakeTransport({ "GET /v1/projects": LIST, "POST /v1/queries/gui-workspace.projects": WORKSPACE });
    open(fake);
    const binding = await screen.findByTestId("workspace-binding");
    expect(binding.textContent).toContain("project_id prj_aaa");
    expect(binding.textContent).toContain("bound here");
    expect(binding.textContent).toContain("plans store: workspace");
    expect(await screen.findByRole("button", { name: "Trust beta at /work/beta" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Trust alpha/ })).toBeNull();
    expect(fake.calls.some((call) => call.method === "POST" && call.path === "/v1/projects")).toBe(false);
  });

  it("trusts only after the confirmation, through POST /v1/projects", async () => {
    let trusted = false;
    const fake = new FakeTransport({
      "GET /v1/projects": () => (trusted ? { ...LIST, projects: [TRUSTED, { id: "p2", name: "beta", root: "/work/beta" }] } : LIST),
      "POST /v1/queries/gui-workspace.projects": WORKSPACE,
      "POST /v1/projects": (call: { body: unknown }) => {
        const body = call.body as { path: string; confirm?: string };
        if (!body.confirm) return new ApiError(409, { code: "CONFIRMATION_REQUIRED", message: "confirm", details: { confirm: "tok", summary: "Trust /work/beta?" } });
        trusted = true;
        return { id: "p2", name: "beta", root: body.path };
      },
    });
    open(fake);
    fireEvent.click(await screen.findByRole("button", { name: "Trust beta at /work/beta" }));
    await screen.findByText("Trust /work/beta?");
    const posts = () => fake.calls.filter((call) => call.method === "POST" && call.path === "/v1/projects");
    expect(posts()).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Trust this project" }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(posts()[1]?.body).toEqual({ path: "/work/beta", confirm: "tok" });
    await waitFor(() => expect(screen.queryByRole("button", { name: /Trust beta/ })).toBeNull());
  });

  it("hides the workspace columns and shows no error when the query is unavailable", async () => {
    const fake = new FakeTransport({ "GET /v1/projects": LIST });
    open(fake);
    await screen.findByText("alpha");
    await waitFor(() => expect(fake.calls.some((call) => call.path === "/v1/queries/gui-workspace.projects")).toBe(true));
    expect(screen.queryByTestId("workspace-binding")).toBeNull();
    expect(screen.queryByText(/not trusted/)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
