import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import type { Trust } from "../contracts/generated/plugin-api";
import { ApiError } from "../transport/ApiError";
import { FakeTransport, Wrapper, type Call } from "../test/fakes";
import { PluginPage } from "./PluginPage";
import { trust } from "../test/plugins";

const DIGEST = `sha256:${"1".repeat(64)}`;
const GRANT = `grant-${"a".repeat(32)}`;
const PROJECTS = { $schema: "urn:swissknifeman:gui:project:v1", kind: "project_list",
  projects: [{ id: "proj-1", name: "Project one", root: "/p", trusted: true, source: "open", added_at: "2026-10-16T10:00:00Z" }] };
const HISTORY = { $schema: "urn:swissknifeman:gui:plugin-api:v1", kind: "plugin_history", plugin: "ext-demo",
  entries: [{ id: 2, at: "2026-10-16T10:00:00Z", kind: "failure", code: "PROCESS_TIMEOUT", detail: "slow" }] };

const PERMISSIONS: Trust["permissions"] = [
  { effect: "read", declared: true, enforcement: "declared" },
  { effect: "network", declared: true, enforcement: "advisory" },
  { effect: "process.spawn", declared: true, enforcement: "advisory" },
  { effect: "terminal", declared: false, enforcement: "declared" },
];

function confirmation(summary: string, risk = "medium"): ApiError {
  return new ApiError(428, { code: "CONFIRMATION_REQUIRED", message: "this request needs a confirmation",
    details: { confirm: "t".repeat(64), risk, summary } });
}

function result(plugin: Trust, drained = 0, cancelled = 0) {
  return { $schema: "urn:swissknifeman:gui:plugin-api:v1", kind: "action_result", plugin, drained, cancelled };
}

function open(fake: FakeTransport) {
  return render(
    <Wrapper transport={fake} path="/plugins/ext-demo">
      <Routes>
        <Route path="/plugins/:pluginId" element={<PluginPage />} />
      </Routes>
    </Wrapper>,
  );
}

const posts = (fake: FakeTransport) => fake.calls.filter((call: Call) => call.method === "POST");

describe("PluginPage", () => {
  it("shows permissions with the enforcement from the API and never says enforced without it", async () => {
    const fake = new FakeTransport({ "GET /v1/plugins/ext-demo*": trust("ext-demo", { permissions: PERMISSIONS }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS });
    const view = open(fake);
    await screen.findByRole("heading", { name: /ext-demo/ });
    const table = within(screen.getByRole("region", { name: "Permissions" }));
    const network = table.getByText("network").closest("tr")!;
    expect(within(network).getByText("advisory")).toBeTruthy();
    expect(within(network).getByText("start requires a grant")).toBeTruthy();
    expect(within(table.getByText("read").closest("tr")!).queryByText("start requires a grant")).toBeNull();
    expect(within(table.getByText("terminal").closest("tr")!).getByText("declared")).toBeTruthy();
    expect(view.container.textContent).not.toMatch(/enforced/i);
    expect(screen.getByText(/PROCESS_TIMEOUT/)).toBeTruthy(); // history
  });

  it("draws an enforced value only when the API sent it", async () => {
    const fake = new FakeTransport({ "GET /v1/plugins/ext-demo*": trust("ext-demo", {
      permissions: [{ effect: "process.spawn", declared: true, enforcement: "enforced" }] }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS });
    open(fake);
    expect(await screen.findByText("enforced")).toBeTruthy();
  });

  it("offers only the declared effects beyond read and terminal and grants after the confirmation", async () => {
    const user = userEvent.setup();
    let granted = false;
    const fake = new FakeTransport({
      "GET /v1/plugins/ext-demo": () => trust("ext-demo", { permissions: PERMISSIONS, grants: granted ? [{ id: GRANT, plugin: "ext-demo",
        capability: "network", project_id: null, manifest_digest: DIGEST, granted_at: "2026-10-16T10:00:00Z",
        expires_at: "2026-10-23T10:00:00Z", granted_by: "browser" }] : [] }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY,
      "GET /v1/projects": PROJECTS,
      "POST /v1/plugins/ext-demo/grants": (call: Call) => {
        if (!(call.body as { confirm?: string }).confirm) throw confirmation("Let ext-demo use network in every project until never.", "high");
        granted = true;
        return { kind: "grant_result" };
      },
    });
    open(fake);
    await user.click(await screen.findByRole("button", { name: "Grant for ext-demo" }));
    const dialog = screen.getByRole("dialog", { name: "Grant for ext-demo" });
    const effects = within(dialog).getByLabelText("Effect");
    expect(within(effects).getAllByRole("option").map((option) => option.textContent)).toEqual(["network", "process.spawn"]);
    await user.selectOptions(within(dialog).getByLabelText("Expires"), "7 days");
    await user.click(within(dialog).getByRole("button", { name: "Grant" }));
    // the backend summary is shown and nothing is repeated until the operator confirms
    const confirm = await screen.findByRole("dialog", { name: "Grant network to ext-demo" });
    expect(confirm.textContent).toContain("Let ext-demo use network in every project");
    expect(confirm.textContent).toContain("high risk");
    expect(posts(fake)).toHaveLength(1);
    const first = posts(fake)[0]!.body as Record<string, unknown>;
    expect(first).toMatchObject({ kind: "grant_request", capability: "network", project_id: null });
    expect(first.expires_at).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/);
    await user.click(within(confirm).getByRole("button", { name: "Confirm and grant" }));
    await waitFor(() => expect(posts(fake)).toHaveLength(2));
    expect(posts(fake)[1]!.body).toEqual({ ...first, confirm: "t".repeat(64) });
    // the details were read again and show the grant
    const grants = within(await screen.findByRole("region", { name: "Grants" }));
    expect(await grants.findByText("2026-10-23T10:00:00Z")).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Grant for ext-demo" })).toBeNull();
  });

  it("sends a grant for one project with no expiry and keeps the dialog on an error", async () => {
    const user = userEvent.setup();
    const fake = new FakeTransport({
      "GET /v1/plugins/ext-demo": trust("ext-demo", { permissions: PERMISSIONS }), "GET /v1/plugins/ext-demo/history?limit=100": HISTORY,
      "GET /v1/projects": PROJECTS,
      "POST /v1/plugins/ext-demo/grants": new ApiError(422, { code: "INPUT_INVALID", message: "not grantable" }),
    });
    open(fake);
    await user.click(await screen.findByRole("button", { name: "Grant for ext-demo" }));
    const dialog = screen.getByRole("dialog", { name: "Grant for ext-demo" });
    await user.selectOptions(within(dialog).getByLabelText("Effect"), "process.spawn");
    await user.selectOptions(within(dialog).getByLabelText("Project"), "Project one");
    await user.click(within(dialog).getByRole("button", { name: "Grant" }));
    expect(await within(dialog).findByText("INPUT_INVALID")).toBeTruthy();
    expect(posts(fake)[0]!.body).toEqual({ $schema: "urn:swissknifeman:gui:plugin-api:v1", kind: "grant_request",
      capability: "process.spawn", project_id: "proj-1", expires_at: null });
  });

  it("says a plugin without grantable effects has nothing to grant", async () => {
    const user = userEvent.setup();
    const fake = new FakeTransport({ "GET /v1/plugins/ext-demo": trust("ext-demo", { permissions: [PERMISSIONS[0]!] }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS });
    open(fake);
    await user.click(await screen.findByRole("button", { name: "Grant for ext-demo" }));
    expect(screen.getByText("This plugin declares no effect that needs a grant.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Grant" })).toBeNull();
  });

  it("revokes a grant", async () => {
    const user = userEvent.setup();
    const grant = { id: GRANT, plugin: "ext-demo", capability: "network" as const, project_id: "proj-1", manifest_digest: DIGEST,
      granted_at: "2026-10-16T10:00:00Z", expires_at: null, granted_by: "cli" };
    let grants = [grant];
    const fake = new FakeTransport({
      "GET /v1/plugins/ext-demo*": () => trust("ext-demo", { permissions: PERMISSIONS, grants }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS,
      [`POST /v1/plugins/ext-demo/grants/${GRANT}:revoke`]: () => {
        grants = [];
        return result(trust("ext-demo"));
      },
    });
    open(fake);
    await user.click(await screen.findByRole("button", { name: "Revoke network grant of ext-demo" }));
    expect(await screen.findByText("No grants.")).toBeTruthy();
    expect(posts(fake)[0]!.body).toEqual({ $schema: "urn:swissknifeman:gui:plugin-api:v1", kind: "action_request" });
  });

  it("disables only after the summary with the number of runs is shown and confirmed", async () => {
    const user = userEvent.setup();
    let state: Trust["state"] = "healthy";
    const fake = new FakeTransport({
      "GET /v1/plugins/ext-demo*": () => trust("ext-demo", { state, runtime_enabled: state === "healthy", permissions: PERMISSIONS }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS,
      "POST /v1/plugins/ext-demo:disable": (call: Call) => {
        if (!(call.body as { confirm?: string }).confirm) {
          throw confirmation("Disable ext-demo: 2 active run(s) are waited for up to 10 s, then cancelled.");
        }
        state = "disabled";
        return result(trust("ext-demo", { state: "disabled", runtime_enabled: false }), 1, 1);
      },
    });
    open(fake);
    await user.click(await screen.findByRole("button", { name: "Disable ext-demo" }));
    const dialog = await screen.findByRole("dialog", { name: "Disable ext-demo" });
    expect(dialog.textContent).toContain("2 active run(s)");
    expect(posts(fake)).toHaveLength(1);
    expect((posts(fake)[0]!.body as { confirm?: string }).confirm).toBeUndefined();
    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Disabled: 1 run(s) finished, 1 cancelled.")).toBeTruthy();
    expect((posts(fake)[1]!.body as { confirm?: string }).confirm).toBe("t".repeat(64));
    expect(await screen.findByRole("button", { name: "Enable ext-demo" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Disable ext-demo" })).toBeNull();
    expect(screen.queryByRole("dialog", { name: "Disable ext-demo" })).toBeNull();
  });

  it("does not repeat a request whose confirmation is cancelled", async () => {
    const user = userEvent.setup();
    const fake = new FakeTransport({
      "GET /v1/plugins/ext-demo*": trust("ext-demo"), "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS,
      "POST /v1/plugins/ext-demo:disable": confirmation("Disable ext-demo: 1 active run(s)."),
    });
    open(fake);
    await user.click(await screen.findByRole("button", { name: "Disable ext-demo" }));
    const dialog = await screen.findByRole("dialog", { name: "Disable ext-demo" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Disable ext-demo" })).toBeNull();
    expect(posts(fake)).toHaveLength(1);
  });

  it("enables an extension and shows the findings of a failed conformance check", async () => {
    const user = userEvent.setup();
    const fake = new FakeTransport({
      "GET /v1/plugins/ext-demo*": trust("ext-demo", { state: "compatible", runtime_enabled: false, ui_enabled: false }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS,
      "POST /v1/plugins/ext-demo:enable": new ApiError(422, { code: "PLUGIN_CONFORMANCE_FAILED", message: "fails the conformance check",
        details: { count: 1, findings: "ext.conformance.describe: no JSON on stdout" } }),
    });
    open(fake);
    expect(screen.queryByRole("button", { name: "Disable ext-demo" })).toBeNull();
    await user.click(await screen.findByRole("button", { name: "Enable ext-demo" }));
    expect(await screen.findByText("PLUGIN_CONFORMANCE_FAILED")).toBeTruthy();
    expect(screen.getByText("ext.conformance.describe: no JSON on stdout")).toBeTruthy();
  });

  it("releases a quarantined plugin", async () => {
    const user = userEvent.setup();
    let state: Trust["state"] = "quarantined";
    const fake = new FakeTransport({
      "GET /v1/plugins/ext-demo*": () => trust("ext-demo", { state, runtime_enabled: state !== "quarantined", ui_enabled: state !== "quarantined",
        failures: { count: state === "quarantined" ? 3 : 0, window_s: 300, last_code: "PROCESS_TIMEOUT" } }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS,
      "POST /v1/plugins/ext-demo:release": () => {
        state = "enabled";
        return result(trust("ext-demo", { state: "enabled" }));
      },
    });
    open(fake);
    const health = within(await screen.findByRole("region", { name: "Health" }));
    expect(health.getByText(/in quarantine after repeated failures/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Enable ext-demo" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Release ext-demo" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Release ext-demo" })).toBeNull());
    expect(screen.getByRole("button", { name: "Disable ext-demo" })).toBeTruthy();
    expect(posts(fake)).toHaveLength(1);
  });

  it("loads project grants for the chosen project", async () => {
    const user = userEvent.setup();
    const fake = new FakeTransport({
      "GET /v1/plugins/ext-demo*": trust("ext-demo", { permissions: PERMISSIONS }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS });
    open(fake);
    await user.selectOptions(await screen.findByLabelText(/Project/), "Project one");
    await waitFor(() => expect(fake.calls.some((call) => call.path === "/v1/plugins/ext-demo?project_id=proj-1")).toBe(true));
  });

  it("says why a plugin that lost its grants cannot run commands", async () => {
    const fake = new FakeTransport({
      "GET /v1/plugins/ext-demo*": trust("ext-demo", { state: "permission_denied", permissions: PERMISSIONS }),
      "GET /v1/plugins/ext-demo/history?limit=100": HISTORY, "GET /v1/projects": PROJECTS });
    open(fake);
    expect(await screen.findByText(/old grants were voided/)).toBeTruthy();
    expect(screen.getAllByText("permission denied").length).toBeGreaterThan(0);
  });
});
