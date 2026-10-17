import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ViewData } from "../contracts";
import { ApiError } from "../transport/ApiError";
import { FakeTransport, Wrapper, type Call } from "../test/fakes";
import { PLAN_ENUMS } from "./plan-enums";
import { SchemaFormView, buildPatch } from "./SchemaFormView";

const fixtures = import.meta.glob("../../../../../bridges/gui-planner/tests/fixtures/plan-enums.json", { eager: true, import: "default" });

type Form = Extract<ViewData, { view: "schema-form" }>;
const REV1 = `sha256:${"1".repeat(64)}`;
const REV2 = `sha256:${"2".repeat(64)}`;
const RUN = `run-${"a".repeat(32)}`;
const DOC = {
  id: "P1.1", title: "Edit me", summary: "Old summary", status: "todo", result: null, depends_on: ["P0.1"], scope: { include: ["a"], exclude: [] },
  review: { mode: "requested", reviewer: { class: "frontier", provider: "codex", model: "gpt-6.1-sol", effort: "high" } },
};
const FORM = {
  id: "gui-planner.item", schema: "urn:swissknifeman:task:plan:item:v1",
  groups: [{ id: "intent", title: "Intent", order: 0 }, { id: "review", title: "Review", order: 10 }, { id: "result", title: "Result", order: 20 }],
  fields: [
    { pointer: "/title", group: "intent", order: 0, widget: "text" },
    { pointer: "/summary", group: "intent", order: 10, widget: "textarea" },
    { pointer: "/depends_on", group: "intent", order: 20, widget: "list" },
    { pointer: "/scope", group: "intent", order: 30, widget: "json" },
    { pointer: "/review/mode", group: "review", order: 0, widget: "select" },
    { pointer: "/review/reviewer/model", group: "review", order: 10, widget: "model-picker" },
    { pointer: "/review/reviewer/provider", group: "review", order: 20, widget: "select" },
    { pointer: "/status", group: "result", order: 0, widget: "text", readonly: true },
    { pointer: "/result", group: "result", order: 10, widget: "json" },
  ],
};
const MODELS = { $schema: "urn:swissknifeman:gui:view-data:v1", view: "resource-list", columns: [{ id: "model", title: "Model", type: "text" }],
  rows: [{ id: "codex/gpt-6.1-sol", cells: { provider: "codex", model: "gpt-6.1-sol" } }, { id: "claude-code/sonnet", cells: { provider: "claude-code", model: "sonnet" } }] };

function data(document: Record<string, unknown> = DOC, revision = REV1): Form {
  return { $schema: "urn:swissknifeman:gui:view-data:v1", view: "schema-form", form: "gui-planner.item", document, revision };
}

function setup(state: { run: unknown; first?: unknown }) {
  const runs: Call[] = [];
  const transport = new FakeTransport({
    "GET /v1/ui/contributions": { $schema: "urn:swissknifeman:gui:catalog:v1", host: { gui_protocol: { min: "1", max: "1" } },
      contributions: [{ owner: "gui-planner", source: { kind: "unit" }, document: { forms: [FORM] } }], rejected: [],
      digest: `sha256:${"0".repeat(64)}` },
    "POST /v1/queries/gui-planner.models": MODELS,
    "POST /v1/queries/gui-planner.item-form": () => data(DOC, REV2),
    "POST /v1/commands/gui-planner.item-set/runs": (call: Call) => {
      runs.push(call);
      if (runs.length === 1 && state.first) return state.first;
      return { run_id: RUN, state: "queued" };
    },
    "GET /v1/runs/*": () => state.run,
  });
  return { transport, runs };
}

function show(transport: FakeTransport, form: Form = data()) {
  return render(
    <Wrapper transport={transport}>
      <SchemaFormView data={form} projectId="proj-1" context={{ plan_id: "PLAN1", item_id: "P1.1" }} />
    </Wrapper>,
  );
}

const failed = (plugin: string) => ({ run_id: RUN, state: "failed", error: { code: "HANDLER_FAILED", details: { plugin_code: plugin } } });
const patchOf = (call: Call) => JSON.parse((call.body as { input: { patch: string } }).input.patch) as Record<string, unknown>;

describe("buildPatch", () => {
  it("sends the changed roots whole and nothing else", () => {
    expect(buildPatch(DOC, { "/summary": "New", "/title": "Edit me", "/scope/include": ["a", "b"] })).toEqual({
      summary: "New", scope: { include: ["a", "b"], exclude: [] } });
  });

  it("merges nested fields into their root and never touches the locked roots", () => {
    const patch = buildPatch(DOC, { "/review/reviewer/model": "sonnet", "/review/reviewer/provider": "claude-code", "/status": "done", "/result": {} });
    expect(patch).toEqual({ review: { mode: "requested", reviewer: { class: "frontier", provider: "claude-code", model: "sonnet", effort: "high" } } });
    expect(buildPatch(DOC, {})).toEqual({});
  });

  it("does not send an empty text for a field that was absent", () => {
    expect(buildPatch(DOC, { "/guidance": "" })).toEqual({});
  });
});

describe("plan-enums.ts", () => {
  it("equals the enum table the planner bridge exports from the planner schema", () => {
    const exported = Object.values(fixtures)[0] as Record<string, string[]>;
    expect(exported).toBeTruthy();
    expect(PLAN_ENUMS).toEqual(exported);
  });
});

describe("SchemaFormView", () => {
  it("shows the groups, keeps the lifecycle fields read-only and has nothing to save at first", async () => {
    const { transport } = setup({ run: { run_id: RUN, state: "succeeded" } });
    show(transport);
    expect(await screen.findByText("Intent")).toBeTruthy();
    expect(screen.getByTestId("ro-status").textContent).toBe("todo");
    expect(screen.queryByLabelText("status")).toBeNull();
    expect(screen.queryByLabelText("result")).toBeNull(); // a lifecycle field is read-only even when annotated as json
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("saves only the changed roots on the revision of the form, and reloads", async () => {
    const { transport, runs } = setup({ run: { run_id: RUN, state: "succeeded" } });
    show(transport);
    fireEvent.change(await screen.findByLabelText("summary"), { target: { value: "New summary" } });
    fireEvent.change(await screen.findByRole("combobox", { name: "review/reviewer/model" }), { target: { value: "claude-code/sonnet" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Saved.");
    expect(runs).toHaveLength(1);
    const body = runs[0]!.body as { context: Record<string, string>; input: { expected_revision: string } };
    expect(body.context).toEqual({ plan_id: "PLAN1", item_id: "P1.1", project_id: "proj-1" });
    expect(body.input.expected_revision).toBe(REV1);
    expect(patchOf(runs[0]!)).toEqual({ summary: "New summary",
      review: { mode: "requested", reviewer: { class: "frontier", provider: "claude-code", model: "sonnet", effort: "high" } } });
  });

  it("shows a model that is not in the catalog as drift and does not replace it", async () => {
    const { transport } = setup({ run: { run_id: RUN, state: "succeeded" } });
    const old = { ...DOC, review: { mode: "requested", reviewer: { ...DOC.review.reviewer, model: "retired-model" } } };
    show(transport, data(old));
    const picker = (await screen.findByRole("combobox", { name: "review/reviewer/model" })) as HTMLSelectElement;
    expect(picker.value).toBe("codex/retired-model");
    expect(screen.getByText(/drift: not in the model catalog/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("a conflict asks first; Reapply sends the same patch on the new revision, only after the click", async () => {
    const state = { run: failed("PLAN_REVISION_CONFLICT") as unknown };
    const { transport, runs } = setup(state);
    show(transport);
    fireEvent.change(await screen.findByLabelText("summary"), { target: { value: "Mine" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "The plan changed" });
    expect(runs).toHaveLength(1);
    state.run = { run_id: RUN, state: "succeeded" };
    fireEvent.click(screen.getByRole("button", { name: "Reapply" }));
    await waitFor(() => expect(runs).toHaveLength(2));
    expect((runs[1]!.body as { input: { expected_revision: string } }).input.expected_revision).toBe(REV2);
    expect(patchOf(runs[1]!)).toEqual(patchOf(runs[0]!));
    await screen.findByText("Saved.");
  });

  it("Reload drops the draft without writing", async () => {
    const { transport, runs } = setup({ run: failed("PLAN_REVISION_CONFLICT") });
    show(transport);
    fireEvent.change(await screen.findByLabelText("summary"), { target: { value: "Mine" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "The plan changed" });
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "The plan changed" })).toBeNull());
    expect(runs).toHaveLength(1);
    expect((screen.getByLabelText("summary") as HTMLTextAreaElement).value).toBe("Old summary");
  });

  it("says why a save was refused", async () => {
    const cases: Array<{ code: string; text: string }> = [{ code: "ITEM_IN_PROGRESS", text: "being executed" },
      { code: "FIELD_NOT_EDITABLE", text: "cannot be edited" }, { code: "SCHEMA_INVALID", text: "do not fit" },
      { code: "PLAN_LOCKED", text: "writing the plan" }, { code: "SOMETHING_ELSE", text: "SOMETHING_ELSE" }];
    for (const { code, text } of cases) {
      const { transport } = setup({ run: failed(code) });
      const view = show(transport);
      fireEvent.change(await screen.findByLabelText("summary"), { target: { value: `x ${code}` } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      expect((await screen.findByRole("status")).textContent).toContain(text);
      view.unmount();
    }
  });

  it("asks for the confirmation of the host and sends it back", async () => {
    const first = new ApiError(428, { code: "CONFIRMATION_REQUIRED", message: "confirm", details: { confirm: "tok-1", risk: "medium", summary: "Edit item" } });
    const { transport, runs } = setup({ run: { run_id: RUN, state: "succeeded" }, first });
    show(transport);
    fireEvent.change(await screen.findByLabelText("summary"), { target: { value: "Mine" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "Confirm the save" });
    fireEvent.click(screen.getByRole("button", { name: "Confirm and save" }));
    await screen.findByText("Saved.");
    expect((runs[1]!.body as { confirm?: string }).confirm).toBe("tok-1");
  });

  it("does not save while a JSON field is not valid JSON", async () => {
    const { transport, runs } = setup({ run: { run_id: RUN, state: "succeeded" } });
    show(transport);
    fireEvent.change(await screen.findByLabelText("depends_on"), { target: { value: "P0.1\nP0.2" } });
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.change(screen.getByLabelText("scope"), { target: { value: "{not json" } });
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
    expect(runs).toHaveLength(0);
  });
});
