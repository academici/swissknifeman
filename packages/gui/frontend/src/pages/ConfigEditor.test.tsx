import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { changed, PROJECT_ID, PROJECTS, projectView } from "../forms/test-fixtures";
import type { ConfigView } from "../forms/types";
import { ApiError } from "../transport/ApiError";
import { FakeTransport, Wrapper, type Call } from "../test/fakes";
import { ConfigEditor } from "./ConfigEditor";
import { ConfigModules } from "./ConfigModules";

const MUTATION = "urn:swissknifeman:gui:config-mutation:v1";
const REV1 = "sha256:" + "2".repeat(64);
const REV2 = "sha256:" + "3".repeat(64);
const VIEW_PATH = `GET /v1/config/config-demo/effective?project_id=${PROJECT_ID}`;
const PREVIEW_PATH = `POST /v1/config/config-demo/preview?project_id=${PROJECT_ID}`;
const COMMIT_PATH = `PATCH /v1/config/config-demo/layers/project?project_id=${PROJECT_ID}`;

function previewDoc(extra: Record<string, unknown> = {}) {
  return {
    $schema: MUTATION, kind: "preview", preview_id: "sha256:" + "a".repeat(64), module: "config-demo", layer: "project",
    file: "/home/user/proj/.swissknifeman/config.toml", revision: REV1,
    diff: [{ key: "limits.max", before: 6, after: 7, effective_before: { value: 6, layer: "project" }, effective_after: { value: 7, layer: "project" } }],
    issues: [], confirm_required: false, confirm_reasons: [], ...extra,
  };
}

const COMMIT_RESULT = { $schema: MUTATION, kind: "commit_result", revision: REV2, file: "/home/user/proj/.swissknifeman/config.toml", backup: null };

function setup(answers: Record<string, unknown | ((call: Call) => unknown)>, view: ConfigView = projectView) {
  const transport = new FakeTransport({ "GET /v1/projects": PROJECTS, [VIEW_PATH]: view, ...answers });
  render(
    <Wrapper transport={transport} path={`/settings/config/config-demo?layer=project&project=${PROJECT_ID}`}>
      <Routes>
        <Route path="/settings/config/:module" element={<ConfigEditor />} />
      </Routes>
    </Wrapper>,
  );
  return transport;
}

const bodies = (transport: FakeTransport, method: string) =>
  transport.calls.filter((call) => call.method === method).map((call) => call.body as Record<string, unknown>);

async function editMax(value: string) {
  const user = userEvent.setup();
  const input = await screen.findByLabelText("limits.max");
  await user.clear(input);
  await user.type(input, value);
  return user;
}

describe("configuration editor", () => {
  it("sends the exact preview request, then commits the preview with the revision of the view", async () => {
    const transport = setup({ [PREVIEW_PATH]: previewDoc(), [COMMIT_PATH]: COMMIT_RESULT });
    const user = await editMax("7");
    await user.click(screen.getByRole("button", { name: "Preview (1)" }));
    await screen.findByRole("dialog", { name: "Preview of the change" });
    await user.click(await screen.findByRole("button", { name: "Apply" }));
    await waitFor(() => expect(bodies(transport, "PATCH")).toHaveLength(1));
    expect(bodies(transport, "POST")[0]).toEqual({
      $schema: MUTATION, kind: "preview_request", module: "config-demo", layer: "project", expected_revision: REV1,
      patch: [{ op: "set", key: "limits.max", value: 7 }],
    });
    expect(bodies(transport, "PATCH")[0]).toEqual({
      $schema: MUTATION, kind: "commit_request", preview_id: "sha256:" + "a".repeat(64), expected_revision: REV1, confirmed: false,
    });
    await screen.findByRole("button", { name: "Preview (0)" }); // the draft is gone, the view is read again
    expect(transport.calls.filter((call) => call.path === VIEW_PATH.slice(4)).length).toBeGreaterThanOrEqual(2);
  });

  it("asks for a confirmation and sends confirmed true", async () => {
    const transport = setup({
      [PREVIEW_PATH]: previewDoc({ confirm_required: true, confirm_reasons: ["secret_key"] }), [COMMIT_PATH]: COMMIT_RESULT,
    });
    const user = await editMax("8");
    await user.click(screen.getByRole("button", { name: "Preview (1)" }));
    expect(await screen.findByText("secret_key")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Confirm and apply" }));
    await waitFor(() => expect(bodies(transport, "PATCH")).toHaveLength(1));
    expect(bodies(transport, "PATCH")[0]).toMatchObject({ confirmed: true });
  });

  it("does not offer Apply while the preview has issues", async () => {
    setup({ [PREVIEW_PATH]: previewDoc({ issues: [{ key: "limits.max", code: "CONFIG_TYPE", message: "above the maximum" }] }) });
    const user = await editMax("500");
    await user.click(screen.getByRole("button", { name: "Preview (1)" }));
    expect(await screen.findByText(/above the maximum/)).toBeTruthy();
    const apply = screen.getByRole("button", { name: "Apply" }) as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
  });

  it("offers no Apply for an earlier draft while the preview of the changed draft is computed", async () => {
    let previews = 0;
    const transport = setup({
      [PREVIEW_PATH]: () => (++previews === 1 ? previewDoc() : new Promise(() => undefined)), [COMMIT_PATH]: COMMIT_RESULT,
    });
    const user = await editMax("7");
    await user.click(screen.getByRole("button", { name: "Preview (1)" }));
    await screen.findByRole("button", { name: "Apply" });
    const input = screen.getByLabelText("limits.max");
    await user.clear(input);
    await user.type(input, "8");
    await waitFor(() => expect(previews).toBeGreaterThan(1));
    expect(screen.queryByRole("button", { name: "Apply" })).toBeNull();
    expect(bodies(transport, "PATCH")).toHaveLength(0);
  });

  it("shows the three-way view on 409 and reapplies on the new revision", async () => {
    const fresh = changed(projectView, (copy) => {
      copy.layers[2]!.revision = REV2;
      const entry = (key: string) => copy.entries.find((candidate) => candidate.key === key)!;
      entry("limits.max").layer_values.project = 9; // the file changed it too: conflict
      entry("mode").layer_values.project = "fast"; // the same change as mine: same
      copy.entries.push({ key: "title", type: "string", secret: false, description: null, allowed_layers: null,
        effective: { value: "theirs", layer: "project", file: null, line: null, source: null }, overridden: [],
        layer_values: { machine: null, project: "theirs" } }); // only the file: theirs
    });
    let reads = 0;
    let previews = 0;
    const transport = setup({
      [VIEW_PATH]: () => (++reads === 1 ? projectView : fresh),
      [PREVIEW_PATH]: () => {
        previews += 1;
        return previews === 1
          ? new ApiError(409, { code: "CONFIG_REVISION_CONFLICT", message: "changed", details: { current_revision: REV2 } })
          : previewDoc({ revision: REV2 });
      },
      [COMMIT_PATH]: COMMIT_RESULT,
    });
    const user = await editMax("7");
    await user.selectOptions(screen.getByLabelText("mode"), "fast");
    await user.click(screen.getByRole("button", { name: "Preview (2)" }));
    const dialog = await screen.findByRole("dialog", { name: "The file changed" });
    const status = (key: string) => within(dialog).getByText(key, { selector: "td" }).closest("tr")!.textContent ?? "";
    expect(status("limits.max")).toContain("conflict");
    expect(status("mode")).toContain("same");
    expect(status("title")).toContain("theirs");
    await user.click(within(dialog).getByRole("button", { name: "Reapply" }));
    await waitFor(() => expect(bodies(transport, "POST")).toHaveLength(2));
    expect(bodies(transport, "POST")[1]).toMatchObject({ expected_revision: REV2, patch: [{ op: "set", key: "limits.max", value: 7 }] });
    await user.click(await screen.findByRole("button", { name: "Apply" }));
    await waitFor(() => expect(bodies(transport, "PATCH")).toHaveLength(1));
    expect(bodies(transport, "PATCH")[0]).toMatchObject({ expected_revision: REV2 });
  });

  it("Reload drops the draft", async () => {
    setup({ [PREVIEW_PATH]: new ApiError(409, { code: "CONFIG_REVISION_CONFLICT", message: "changed" }) });
    const user = await editMax("7");
    await user.click(screen.getByRole("button", { name: "Preview (1)" }));
    const dialog = await screen.findByRole("dialog", { name: "The file changed" });
    await user.click(within(dialog).getByRole("button", { name: "Reload" }));
    await screen.findByRole("button", { name: "Preview (0)" });
  });

  it("explains a locked file and lets the user apply again", async () => {
    let commits = 0;
    const transport = setup({
      [PREVIEW_PATH]: previewDoc(),
      [COMMIT_PATH]: () => (++commits === 1 ? new ApiError(423, { code: "CONFIG_LOCKED", message: "locked", retryable: true }) : COMMIT_RESULT),
    });
    const user = await editMax("7");
    await user.click(screen.getByRole("button", { name: "Preview (1)" }));
    await user.click(await screen.findByRole("button", { name: "Apply" }));
    expect(await screen.findByText(/holds the lock/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(bodies(transport, "PATCH")).toHaveLength(2));
  });

  it("disables a field whose key may not be set in the layer", async () => {
    setup({});
    const input = (await screen.findByLabelText("cache_dir")) as HTMLInputElement;
    expect(input.disabled).toBe(true);
    expect(screen.getByText("allowed: defaults, machine")).toBeTruthy();
  });

  it("shows an unsupported keyword as read-only", async () => {
    setup({}, changed(projectView, (copy) => {
      (copy.schema as { properties: Record<string, unknown> }).properties["title"] = { type: "string", format: "uri" };
    }));
    expect(await screen.findByText(/unsupported: format/)).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "title" })).toBeNull();
  });

  it("sends only a reference for a secret key", async () => {
    const transport = setup({ [PREVIEW_PATH]: previewDoc() });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("token"), "MY_TOKEN");
    await user.click(screen.getByRole("button", { name: "Preview (1)" }));
    await waitFor(() => expect(bodies(transport, "POST")).toHaveLength(1));
    expect(bodies(transport, "POST")[0]).toMatchObject({ patch: [{ op: "set", key: "token", value: "env://MY_TOKEN" }] });
  });

  it("switches between Form, Diff, Raw and Explain", async () => {
    setup({});
    const user = await editMax("7");
    await user.click(screen.getByRole("tab", { name: "Diff" }));
    expect(await screen.findByText("limits.max")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Raw" }));
    expect((await screen.findByTestId("raw")).textContent).toContain("max = 6");
    await user.click(screen.getByRole("tab", { name: "Explain" }));
    expect(await screen.findByTestId("prov-mode")).toBeTruthy();
  });
});

describe("configuration modules", () => {
  it("lists the modules with a link to the editor", async () => {
    const transport = new FakeTransport({
      "GET /v1/config": { $schema: "urn:swissknifeman:gui:config-view:v1", kind: "config_modules", modules: [{ id: "config-demo", title: "config-demo config", description: null }] },
    });
    render(<Wrapper transport={transport}><ConfigModules /></Wrapper>);
    const link = (await screen.findByRole("link", { name: "config-demo" })) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/settings/config/config-demo");
  });
});
