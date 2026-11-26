// @vitest-environment jsdom
import { execFileSync } from "node:child_process";
import { URL as NodeURL, fileURLToPath } from "node:url";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";
import { App } from "../../app/App";

const basePath = "/api/v1/plans/plan/drafts/draft";
const fixtureId = (id: number) => `01234567-89ab-7000-8000-${String(id).padStart(12, "0")}`;
const phase = { id: fixtureId(1), key: "P1", title: "Retry phase", goal: "Retry deliveries", design_state: "detailed" };
const item = {
  id: fixtureId(2), key: "P1.1", phase: "P1", title: "Retry loop", summary: "Retry deliveries", why: "Prevent lost deliveries",
  review: { mode: "required" }, work_policy: { role_intensity: { executor: "heavy", reviewer: "light" } },
};
const sibling = { ...item, id: fixtureId(3), key: "P1.2", title: "Backoff" };
const parent = { id: fixtureId(4), key: "P1.1/U1", title: "Parent unit", goal: "Prepare", work_policy: { verification_intensity: "heavy" } };
const child = {
  id: fixtureId(5), key: "P1.1/U2", title: "Child unit", goal: "Implement", parent: "U1",
  work_policy: { verification_intensity: "light" },
};

type Document = Record<string, unknown> & {
  phases: Record<string, unknown>[];
  items: Record<string, unknown>[];
  units: Record<string, unknown>[];
};
const initial: Document = {
  schema: "urn:skm:planning:specification:v1", title: "Delivery plan", goal: "Reliable delivery",
  phases: [phase], items: [item, sibling], units: [parent, child],
};

type Call = { route: string; method: string; body: Record<string, unknown>; headers: Headers };
type Handler = (call: Call) => Response | Promise<Response> | undefined;

function validation(version: number, message?: string) {
  return {
    edit_version: version, schema_issues: [], rule_failures: message ? [{ rule: "check-rule", message: "Rule failure", error_type: "timeout" }] : [],
    findings: message ? [{
      code: "NEEDS_WORK", severity: "warning", message, entity_id: item.id, entity_key: item.key, pointer: "/items/0/summary",
    }] : [],
  };
}

function problem(status: number, code: string, details: Record<string, unknown>) {
  return Response.json({ code, request_id: "draft-request", details, category: status === 409 ? "conflict" : "validation", detail: code },
    { status, headers: { "Content-Type": "application/problem+json" } });
}

function setup(handler: Handler = () => undefined, { document = initial, scoped = false, current = "r1" } = {}) {
  const calls: Call[] = [];
  const events: string[] = [];
  let cursor = 9;
  const streams = new Map<string, ReadableStreamDefaultController<Uint8Array>>();
  const draft = {
    draft_id: "draft", state: "open", edit_version: 1, base_revision_id: "r1", base_revision_no: 1, stale: false,
    document: structuredClone(document),
  };
  const plan = {
    plan_id: "plan", alias: "PLAN1", current_revision_id: current, lifecycle_state: "active",
    ...(scoped ? { workspace_id: "ws", project_id: "project" } : {}),
  };
  const snapshot = (data: unknown) => Response.json(data, { headers: { "SKM-Events-Cursor": String(cursor) } });
  stubFetch(async (input, init) => {
    const url = new URL(String(input), window.location.origin);
    const method = init?.method ?? "GET";
    const { pathname } = url;
    if (pathname === "/api/v1/me") return Response.json({ ...testIdentity, permissions_by_scope: { plan: ["plan.edit", "plan.publish"] } });
    if (pathname === "/api/v1/workspaces/ws") return snapshot({ workspace_id: "ws", title: "Workspace" });
    if (pathname === "/api/v1/projects/project") return snapshot({ project_id: "project", workspace_id: "ws", title: "Project" });
    if (pathname === "/api/v1/plans/plan") return snapshot(plan);
    if (pathname === "/api/v1/events") {
      events.push(url.searchParams.get("after") ?? "");
      const filter = url.searchParams.get("types") ?? "";
      return new Response(new ReadableStream({
        start(controller) { streams.set(filter, controller); },
        cancel() { streams.delete(filter); },
      }),
        { headers: { "Content-Type": "text/event-stream" } });
    }
    if (pathname === "/api/v1/config/explain") {
      expect(url.searchParams.get("scope")).toBe("plan:plan");
      expect(url.searchParams.getAll("key").length).toBeLessThanOrEqual(1);
      const keys = [{
        key: "execution.work_policy.role_intensity", value: { executor: "medium", scout: "light" },
        winner: { level: "project", label: "Defaults" }, locked_by: { level: "workspace", label: "Policy" }, contributions: [],
      }, {
        key: "execution.work_policy.verification_intensity", value: "medium", winner: { level: "default" },
        locked_by: { level: "workspace", label: "Verification" }, contributions: [],
      }];
      const section = url.searchParams.get("section");
      const key = url.searchParams.get("key");
      return snapshot({ keys: keys.filter((entry) => key ? entry.key === key : section === "execution") });
    }
    if (!pathname.startsWith(basePath)) throw new Error(pathname);
    const route = pathname.slice(basePath.length);
    const body = JSON.parse(String(init?.body ?? "{}"));
    const call = { route, method, body, headers: new Headers(init?.headers) };
    calls.push(call);
    const response = handler(call);
    if (response) return response;
    if (route === "/validate") return Response.json(validation(Number(body.expected_edit_version)));
    if (!route && method === "GET") return snapshot(draft);
    throw new Error(`${method} ${pathname}`);
  });
  history.replaceState(null, "", "/plans/plan/drafts/draft" + (scoped ? "?workspace_id=ws&project_id=project" : ""));
  render(<App initialToken="token" />);
  return {
    calls, draft, events, snapshot, user: userEvent.setup(),
    send(type: string, payload: Record<string, unknown>) {
      cursor += 1;
      const eventType = `urn:skm:planning:event:${type}:v1`;
      const frame = new TextEncoder().encode(`id: ${cursor}\nevent: domain\ndata: ${JSON.stringify({
        type: eventType, stream_kind: "plan", stream_id: "plan", workspace_id: "ws",
        payload: { plan_id: "plan", ...payload },
      })}\n\n`);
      for (const [filter, stream] of streams) if (!filter || filter === eventType) stream.enqueue(frame);
    },
  };
}

function textbox(name: string) {
  return screen.getByRole<HTMLInputElement>("textbox", { name });
}

function button(name: string | RegExp) {
  return screen.getByRole<HTMLButtonElement>("button", { name });
}

async function selectItem(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByText("P1 · Retry phase", { selector: "summary" }, { timeout: 5000 }));
  await user.click(screen.getByText("P1.1 · Retry loop", { selector: "summary" }));
  await user.click(button("Открыть P1.1 · Retry loop"));
}

function saveResult(version: number, assigned_ids: unknown[] = []) {
  return Response.json({ draft_id: "draft", edit_version: version, document_digest: "saved", assigned_ids });
}

function applyServerChanges(document: Document, call: Call): { document: Document } |
  { status: number; code: string; details: Record<string, unknown> } {
  // Exercise the production command and DraftView schemas plus the server's ordered batch application.
  const script = `
import json
import sys
from starlette.requests import Request
from skm.entrypoints.api.errors import problem_response
from skm.kernel.errors import SkmError
from skm.modules.planning.application.commands.save_draft import _domain_change
from skm.modules.planning.domain.changes import ItemDefaults, apply_changes
from skm.modules.planning.domain.item import Effort, ModelClass
from skm.modules.planning.domain.review_requirement import ReviewMode
from skm.modules.planning.generated.commands import SaveDraft
from skm.platform.schema.registry import SchemaRegistry

request, snapshot = json.load(sys.stdin)
schemas = SchemaRegistry.load_default()
draft_urn = "urn:skm:planning:view:draft:v1"
try:
    schemas.require_valid("urn:skm:planning:command:save-draft:v1", request)
    schemas.require_valid(draft_urn, snapshot)
    command = SaveDraft.from_json(request)
    result = apply_changes(
        snapshot["document"], [_domain_change(change) for change in command.changes],
        defaults=ItemDefaults(ModelClass.IMPLEMENTATION, Effort.MEDIUM, ReviewMode.REQUIRED),
        validate=lambda doc: schemas.require_valid("urn:skm:planning:specification:v1", doc),
    )
    schemas.require_valid(draft_urn, {**snapshot, "document": result.document})
    print(json.dumps({"document": result.document}))
except SkmError as error:
    print(problem_response(Request({"type": "http", "path": "/changes"}), error).body.decode())
`;
  const actor = fixtureId(6), draftId = fixtureId(7), revision = fixtureId(8), planId = fixtureId(9);
  const version = Number(call.headers.get("If-Match")?.match(/v(\d+)/u)?.[1]);
  return JSON.parse(execFileSync("uv", ["run", "--frozen", "python", "-c", script], {
    cwd: fileURLToPath(new NodeURL("../../../../", import.meta.url)), encoding: "utf8", input: JSON.stringify([
      { draft_id: draftId, plan_id: planId, expected_edit_version: version, ...call.body },
      {
        draft_id: draftId, edit_version: version, document, state: "open", stale: false,
        base_revision_id: revision, base_revision_no: 1, published_revision_id: null, closed_at: null,
        created_by: actor, updated_by: actor, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
        document_digest: "sha256:" + "0".repeat(64),
      },
    ]),
  }));
}

function preview(version: number, candidate = "one") {
  return Response.json({
    source: { kind: "draft", draft_id: "draft", plan_id: "plan", edit_version: version },
    base_revision_id: "r1", content_digest: `digest-${candidate}`, publishable: true, no_changes: false,
    pinned_materials: [{ material_key: "spec", file_version_id: `pin-${candidate}`, resolved_from: "latest_at_publish" }],
    diff: { plan_fields: [{ pointer: "/goal", op: "replace", before: "previous", after: `prepared-${candidate}` }], entities: [] },
    validation: { findings: [], rule_failures: [] },
  });
}

it("keeps edits after schema errors, then validates the saved version and focuses the finding field", async () => {
  let attempted = false;
  const editor = setup((call) => {
    if (call.method === "PATCH") {
      if (!attempted) {
        attempted = true;
        return problem(422, "SCHEMA_INVALID", { issues: [{ pointer: "/items/0/summary", message: "Fix the summary" }] });
      }
      editor.draft.document = { ...editor.draft.document, ...call.body };
      editor.draft.edit_version = 2;
      return saveResult(2);
    }
    if (call.route === "/validate" && call.body.expected_edit_version === 2) {
      return Response.json(validation(2, "<img src=x onerror=alert(1)>\u202e"));
    }
  });
  await selectItem(editor.user);
  fireEvent.change(textbox("summary"), { target: { value: "Improved summary" } });
  expect(button("Publish…").disabled).toBe(true);
  await editor.user.click(button("Save"));
  const issue = await screen.findByText("Fix the summary");
  expect(issue.closest("[data-pointer]")?.getAttribute("data-pointer")).toBe("/items/0/summary");
  expect(textbox("summary").value).toBe("Improved summary");
  expect(textbox("summary").getAttribute("aria-invalid")).toBe("true");
  await editor.user.click(button("Save"));
  const finding = await screen.findByRole("button", { name: /NEEDS_WORK.*onerror=.*\\u202e/ });
  await editor.user.click(finding);
  expect(document.activeElement).toBe(textbox("summary"));
  expect(document.querySelector("img")).toBeNull();
  expect(screen.getByText(/Rule failure/)).toBeTruthy();
  const patches = editor.calls.filter((call) => call.method === "PATCH");
  expect(patches).toHaveLength(2);
  expect(patches[1]?.headers.get("Content-Type")).toBe("application/merge-patch+json");
  expect(patches[1]?.headers.get("If-Match")).toBe('W/"v1"');
  expect(patches[1]?.body).toEqual({ items: [{ ...item, summary: "Improved summary" }, sibling] });
  expect(editor.calls.some((call) => call.route === "/validate" && call.body.expected_edit_version === 2)).toBe(true);
});

it("creates all six structural skeletons with server-owned IDs omitted", async () => {
  const editor = setup((call) => {
    if (call.method !== "PATCH") return;
    editor.draft.document = { ...editor.draft.document, ...call.body };
    editor.draft.edit_version = 2;
    return saveResult(2);
  });
  await screen.findByRole("heading", { name: "Delivery plan" });
  for (const action of ["Phase", "Item", "Unit", "Check", "Decision", "Requirement"]) await editor.user.click(button("+ " + action));
  await editor.user.click(button("Save"));
  await waitFor(() => expect(editor.draft.edit_version).toBe(2));
  const body = editor.calls.find((call) => call.method === "PATCH")!.body as Document;
  expect(body.phases).toEqual([phase, { key: "P2", title: "Новая фаза", goal: "Цель фазы", design_state: "skeleton" }]);
  expect(body.items.at(-1)).toMatchObject({ phase: "P2", key: "P2.1", review: { mode: "required" } });
  expect(body.units.at(-1)).toMatchObject({ key: "P2.1/U1" });
  for (const collection of ["phases", "items", "units", "checks", "decisions", "requirements"]) {
    const members = body[collection] as Record<string, unknown>[];
    expect(members.at(-1)).not.toHaveProperty("id");
  }
  expect(body.items[0]?.id).toBe(item.id);
});

it("atomically batches a display-key rename with ordinary edits, keeping the saved tree key until success", async () => {
  const editor = setup((call) => {
    if (call.route !== "/changes") return;
    editor.draft.edit_version = 2;
    editor.draft.document.items[0] = { ...item, key: "P1.8", summary: "Rename and edit",
      work_policy: { role_intensity: { reviewer: "light" } } };
    return saveResult(2);
  });
  await selectItem(editor.user);
  fireEvent.change(textbox("key"), { target: { value: "P1.8" } });
  fireEvent.change(textbox("summary"), { target: { value: "Rename and edit" } });
  await editor.user.selectOptions(screen.getByRole("combobox", { name: "executor" }), "Наследовать");
  expect(button("Открыть P1.1 · Retry loop *")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Открыть P1.8/ })).toBeNull();
  await editor.user.click(button("Save"));
  await screen.findByRole("heading", { name: "P1.8 · item" });
  const save = editor.calls.find((call) => call.route === "/changes")!;
  expect(save.method).toBe("POST");
  expect(save.headers.get("If-Match")).toBe('W/"v1"');
  expect(save.body.changes).toEqual([
    { op: "patch", target: "P1.1", merge_patch: {
      summary: "Rename and edit", work_policy: { role_intensity: { executor: null } },
    } },
    { op: "rekey", target: "P1.1", new_key: "P1.8" },
  ]);
});

it.each([
  { destination: "P1.3", label: "orders a rename chain", operations: 2 },
  { destination: "P1.2", label: "breaks a rename cycle", operations: 3 },
])("$label in one CAS batch with the real server changes contract", async ({ destination, operations }) => {
  const editor = setup((call) => {
    if (call.route !== "/changes") return;
    const result = applyServerChanges(editor.draft.document, call);
    if ("code" in result) return problem(result.status, result.code, result.details);
    editor.draft.document = result.document;
    editor.draft.edit_version = 2;
    return saveResult(2);
  });
  await selectItem(editor.user);
  fireEvent.change(textbox("key"), { target: { value: destination } });
  await editor.user.click(button("P1.2 · Backoff"));
  fireEvent.change(textbox("key"), { target: { value: "P1.1" } });
  await editor.user.click(button("Save"));
  await screen.findByRole("heading", { name: "P1.1 · item" });
  const saves = editor.calls.filter((call) => call.route === "/changes");
  expect(saves).toHaveLength(1);
  expect(saves[0]?.headers.get("If-Match")).toBe('W/"v1"');
  expect(saves[0]?.body.changes).toHaveLength(operations);
  expect(editor.draft.document.items.map(({ id, key }) => [id, key])).toEqual([[item.id, destination], [sibling.id, "P1.1"]]);
  expect(editor.draft.document.units.map(({ key }) => key)).toEqual([`${destination}/U1`, `${destination}/U2`]);
});

it("maps typed-batch issues back to rows after an add shifts server positions", async () => {
  const nextPhase = { ...phase, id: fixtureId(10), key: "P2", title: "Release phase" };
  const release = { ...sibling, key: "P2.1", phase: "P2", title: "Release" };
  const editor = setup((call) => {
    if (call.route !== "/changes") return;
    const result = applyServerChanges(editor.draft.document, call);
    if (!("code" in result)) throw new Error("Expected the server schema to reject the title");
    expect(result.code).toBe("SCHEMA_INVALID");
    expect(result.details.issues).toEqual(expect.arrayContaining([expect.objectContaining({ pointer: "/items/1/title" })]));
    return problem(422, result.code, { ...result.details, issues: [
      ...(result.details.issues as unknown[]),
      { pointer: "/items/2/summary", message: "Check the existing release item" },
      { pointer: "/items/9/title", message: "Row could not be addressed" },
      { pointer: "/goal", message: "Overall goal needs attention" },
    ] });
  }, { document: { ...initial, phases: [phase, nextPhase], items: [item, release] } });
  await selectItem(editor.user);
  fireEvent.change(textbox("key"), { target: { value: "P1.8" } });
  await editor.user.click(button("+ Item"));
  fireEvent.change(textbox("title"), { target: { value: "" } });
  await editor.user.click(button("Save"));
  await screen.findByText(/Row could not be addressed/);
  expect(screen.getByText(/Overall goal needs attention/)).toBeTruthy();
  expect(textbox("title").getAttribute("aria-invalid")).toBe("true");
  expect(textbox("title").value).toBe("");
  await editor.user.click(screen.getByText("P2 · Release phase", { selector: "summary" }));
  await editor.user.click(button("P2.1 · Release"));
  expect(screen.getByText("Check the existing release item").closest("[data-pointer]")?.getAttribute("data-pointer")).toBe("/items/1/summary");
  expect(textbox("title").getAttribute("aria-invalid")).toBeNull();
});

it("resolves both policy keys and uses null patches that pass the real Changes and Draft schemas", async () => {
  const editor = setup((call) => {
    if (call.route !== "/changes") return;
    const result = applyServerChanges(editor.draft.document, call);
    if ("code" in result) return problem(result.status, result.code, result.details);
    editor.draft.document = result.document;
    editor.draft.edit_version = 2;
    return saveResult(2);
  });
  await selectItem(editor.user);
  await screen.findAllByText(/Блокировка · workspace · Policy/);
  expect(screen.getByText("Наследуется medium · project · Defaults.")).toBeTruthy();
  expect(screen.getByText("Блокировка · workspace · Verification.")).toBeTruthy();
  expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "executor" }).value).toBe("heavy");
  await editor.user.selectOptions(screen.getByRole("combobox", { name: "executor" }), "Наследовать");
  await editor.user.click(button("P1.1/U2 · Child unit"));
  expect(screen.getByText("Наследуется medium · default.")).toBeTruthy();
  expect(screen.getByText("Наследуется light от Item.")).toBeTruthy();
  await editor.user.selectOptions(screen.getByRole("combobox", { name: "verification_intensity" }), "Наследовать");
  await editor.user.click(button("Save"));
  await waitFor(() => expect(editor.draft.edit_version).toBe(2));
  const save = editor.calls.find((call) => call.route === "/changes")!;
  expect(save.headers.get("If-Match")).toBe('W/"v1"');
  expect(save.body.changes).toEqual([
    { op: "patch", target: "P1.1", merge_patch: { work_policy: { role_intensity: { executor: null } } } },
    { op: "patch", target: "P1.1/U2", merge_patch: { work_policy: { verification_intensity: null } } },
  ]);
  expect(editor.draft.document.items).toEqual([{ ...item, work_policy: { role_intensity: { reviewer: "light" } } }, sibling]);
  expect(editor.draft.document.units).toEqual([parent, { ...child, work_policy: {} }]);
});

it("keeps findings from the newer save when an older validation completes late", async () => {
  let finish!: (response: Response) => void;
  const pending = new Promise<Response>((resolve) => { finish = resolve; });
  const editor = setup((call) => {
    if (call.route === "/validate") return call.body.expected_edit_version === 1
      ? pending : Response.json(validation(2, "New findings"));
    if (call.method === "PATCH") {
      editor.draft.edit_version = 2;
      return saveResult(2);
    }
  });
  await selectItem(editor.user);
  fireEvent.change(textbox("summary"), { target: { value: "New summary" } });
  await editor.user.click(button("Save"));
  await screen.findByRole("button", { name: /New findings/ });
  await act(async () => finish(Response.json(validation(1, "Old findings"))));
  expect(screen.queryByRole("button", { name: /Old findings/ })).toBeNull();
});

it("keeps the local policy change on a CAS conflict and reapplies it to the fetched item", async () => {
  const editor = setup((call) => {
    if (call.route !== "/changes") return;
    if (call.headers.get("If-Match") === 'W/"v1"') {
      editor.draft.edit_version = 2;
      editor.draft.document.items[0] = { ...item, title: "Remote title", work_policy: {
        role_intensity: { executor: "heavy", reviewer: "medium" }, verification_intensity: "heavy",
      } };
      return problem(409, "VERSION_CONFLICT", { current_edit_version: 2 });
    }
    const result = applyServerChanges(editor.draft.document, call);
    if ("code" in result) return problem(result.status, result.code, result.details);
    editor.draft.document = result.document;
    editor.draft.edit_version = 3;
    return saveResult(3);
  });
  await selectItem(editor.user);
  await editor.user.selectOptions(screen.getByRole("combobox", { name: "executor" }), "Наследовать");
  await editor.user.click(button("Save"));
  const conflict = within(await screen.findByRole("alert"));
  expect(conflict.getByRole("heading", { name: "Конфликт изменений" })).toBeTruthy();
  expect(conflict.getByText("VERSION_CONFLICT", { exact: true })).toBeTruthy();
  expect(conflict.getByText("draft-request", { exact: true })).toBeTruthy();
  expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "executor" }).value).toBe("");
  await editor.user.click(button("Загрузить текущую версию"));
  await waitFor(() => expect(textbox("title").value).toBe("Remote title"));
  expect(screen.getByRole<HTMLSelectElement>("combobox", { name: "reviewer" }).value).toBe("medium");
  await editor.user.click(button("Save"));
  await waitFor(() => expect(editor.draft.edit_version).toBe(3));
  const patches = editor.calls.filter((call) => call.route === "/changes");
  expect(patches[1]?.headers.get("If-Match")).toBe('W/"v2"');
  expect(editor.draft.document.items).toEqual([{ ...item, title: "Remote title", work_policy: {
    role_intensity: { reviewer: "medium" }, verification_intensity: "heavy",
  } }, sibling]);
});

it("requires a choice for each overlapping field after loading a newer draft", async () => {
  const editor = setup((call) => {
    if (call.method !== "PATCH") return;
    if (call.headers.get("If-Match") === 'W/"v1"') {
      editor.draft.edit_version = 2;
      editor.draft.document.items[0] = { ...item, title: "Remote title", summary: "Remote summary", why: "Remote rationale" };
      return problem(409, "VERSION_CONFLICT", { current_edit_version: 2 });
    }
    editor.draft.document = { ...editor.draft.document, ...call.body };
    editor.draft.edit_version = 3;
    return saveResult(3);
  });
  await selectItem(editor.user);
  fireEvent.change(textbox("title"), { target: { value: "Local title" } });
  fireEvent.change(textbox("summary"), { target: { value: "Local summary" } });
  await editor.user.click(button("Save"));
  await editor.user.click(await screen.findByRole("button", { name: "Загрузить текущую версию" }));
  const conflicts = within(await screen.findByRole("region", { name: "Конфликты локальных правок" }));
  expect(textbox("why").value).toBe("Remote rationale");
  expect(button("Save").disabled).toBe(true);
  await editor.user.click(within(conflicts.getByRole("group", { name: "P1.1 · /title" })).getByRole("button", { name: "Принять текущее" }));
  expect(button("Save").disabled).toBe(true);
  await editor.user.click(within(conflicts.getByRole("group", { name: "P1.1 · /summary" })).getByRole("button", { name: "Оставить своё" }));
  expect(textbox("title").value).toBe("Remote title");
  expect(textbox("summary").value).toBe("Local summary");
  expect(button("Save").disabled).toBe(false);
  await editor.user.click(button("Save"));
  await waitFor(() => expect(editor.draft.edit_version).toBe(3));
  expect(editor.calls.filter((call) => call.method === "PATCH")[1]?.headers.get("If-Match")).toBe('W/"v2"');
  expect(editor.draft.document.items[0]).toMatchObject({ title: "Remote title", summary: "Local summary", why: "Remote rationale" });
});

it("replays the exact publish request after network loss and refreshes a changed candidate only on request", async () => {
  let preparations = 0;
  let publishes = 0;
  const editor = setup((call) => {
    if (call.route === "/publication-preview") return preview(1, ++preparations === 1 ? "one" : "two");
    if (call.route === "/publish") {
      publishes += 1;
      if (publishes === 1) throw new Error("Connection lost");
      if (publishes === 2) return problem(409, "VERSION_CONFLICT", { reason: "candidate_changed" });
      editor.draft.state = "published";
      return Response.json({ revision_id: "r2", revision_no: 2 }, { status: 201 });
    }
  });
  await editor.user.click(await screen.findByRole("button", { name: "Publish…" }));
  const dialog = await screen.findByRole("dialog", { name: "Публикация черновика" });
  await within(dialog).findByText("pin-one");
  expect(within(dialog).getByText('"prepared-one"')).toBeTruthy();
  expect(editor.calls.find((call) => call.route === "/publication-preview")?.body).toEqual({ expected_edit_version: 1 });
  expect(button("Publish shown changes").disabled).toBe(true);
  await editor.user.type(textbox("Причина публикации"), "Prepared release");
  await editor.user.click(button("Publish shown changes"));
  await editor.user.click(await screen.findByRole("button", { name: "Повторить публикацию" }));
  await screen.findByText("Prepared content changed");
  expect(preparations).toBe(1);
  expect(button("Publish shown changes").disabled).toBe(true);
  const requests = () => editor.calls.filter((call) => call.route === "/publish");
  expect(requests()[0]?.body).toEqual({ expected_content_digest: "digest-one", reason: "Prepared release" });
  expect(requests()[0]?.headers.get("If-Match")).toBe('W/"v1"');
  expect(requests()[0]?.headers.get("Idempotency-Key")).toBeTruthy();
  expect(requests()[1]?.body).toEqual(requests()[0]?.body);
  expect(requests()[1]?.headers.get("If-Match")).toBe(requests()[0]?.headers.get("If-Match"));
  expect(requests()[1]?.headers.get("Idempotency-Key")).toBe(requests()[0]?.headers.get("Idempotency-Key"));
  await editor.user.click(button("Refresh preview"));
  await within(await screen.findByRole("dialog")).findByText("pin-two");
  expect(publishes).toBe(2);
  await editor.user.click(button("Publish shown changes"));
  expect(await screen.findByRole("link", { name: "ревизия r2" })).toBeTruthy();
  expect(requests()[2]?.body.expected_content_digest).toBe("digest-two");
  expect(requests()[2]?.headers.get("Idempotency-Key")).not.toBe(requests()[0]?.headers.get("Idempotency-Key"));
});

it("allows the exact publish replay after SSE reports a commit whose response was lost", async () => {
  let submitted = false;
  const editor = setup((call) => {
    if (call.route === "/publication-preview") return preview(1);
    if (call.route !== "/publish") return;
    if (!submitted) {
      submitted = true;
      editor.draft.state = "published";
      editor.send("plan-revision-published", { draft_id: "draft", revision_id: "r2" });
      throw new Error("Lost publication receipt");
    }
    return Response.json({ revision_id: "r2", revision_no: 2 }, { status: 201 });
  }, { scoped: true });
  await editor.user.click(await screen.findByRole("button", { name: "Publish…" }));
  await screen.findByText("pin-one");
  await editor.user.type(textbox("Причина публикации"), "Publish this candidate");
  await editor.user.click(button("Publish shown changes"));
  await screen.findByText("Черновик закрыт или план архивирован.");
  expect(button("Publish shown changes").disabled).toBe(true);
  await editor.user.click(button("Повторить публикацию"));
  expect(await screen.findByRole("link", { name: "ревизия r2" })).toBeTruthy();
  const requests = editor.calls.filter((call) => call.route === "/publish");
  expect(requests[1]?.body).toEqual(requests[0]?.body);
  expect(requests[1]?.headers.get("Idempotency-Key")).toBe(requests[0]?.headers.get("Idempotency-Key"));
  expect(requests[1]?.headers.get("If-Match")).toBe(requests[0]?.headers.get("If-Match"));
});

it("pins rebase to the reported revision, applies choices and retains unsaved edits across the server rebase", async () => {
  let submitted = false;
  const editor = setup((call) => {
    if (call.route === "/publication-preview") return problem(409, "BASE_REVISION_CHANGED", { current_revision_id: "r2" });
    if (call.route !== "/rebase") return;
    if (!submitted) {
      submitted = true;
      return problem(409, "REBASE_CONFLICTS", { current_revision_id: "r2", edit_version: 1, conflicts: [
        { conflict_id: "title", kind: "field", key: "P1.1", field: "title", pointer: "/items/0/title",
          base: "base title", yours: "draft title", theirs: "revision title", resolutions: ["yours", "theirs"] },
        { conflict_id: "collision", kind: "key_collision", key: "P1.2", field: "key", resolutions: ["rekey"] },
      ] });
    }
    editor.draft.edit_version = 2;
    editor.draft.base_revision_id = "r2";
    editor.draft.base_revision_no = 2;
    editor.draft.document.items[0] = { ...item, title: "revision title", summary: "Rebased summary" };
    return Response.json({ edit_version: 2, base_revision_id: "r2" });
  }, { current: "r2" });
  await selectItem(editor.user);
  await editor.user.click(button("Publish…"));
  const previewDialog = await screen.findByRole("dialog", { name: "Публикация черновика" });
  await editor.user.click(await within(previewDialog).findByRole("button", { name: "Rebase" }));
  expect(await screen.findByRole("dialog", { name: "Rebase черновика" })).toBeTruthy();
  await editor.user.click(button("Закрыть"));
  fireEvent.change(textbox("summary"), { target: { value: "Still editing" } });
  await editor.user.click(button("Rebase"));
  await editor.user.click(button("Начать rebase"));
  const table = within(await screen.findByRole("table"));
  for (const side of ["base", "yours", "theirs"]) expect(table.getByRole("columnheader", { name: side })).toBeTruthy();
  expect(table.getByText('"base title"')).toBeTruthy();
  expect(table.getByText('"draft title"')).toBeTruthy();
  expect(table.getByText('"revision title"')).toBeTruthy();
  await editor.user.selectOptions(table.getByRole("combobox", { name: "Решение · P1.1" }), "theirs");
  await editor.user.type(table.getByRole("textbox", { name: "Решение · P1.2" }), "P1.3");
  await editor.user.click(button("Применить решения"));
  await waitFor(() => expect(textbox("title").value).toBe("revision title"));
  expect(button("Save").disabled).toBe(true);
  const overlap = within(await screen.findByRole("group", { name: "P1.1 · /summary" }));
  expect(overlap.getByText('"Rebased summary"')).toBeTruthy();
  await editor.user.click(overlap.getByRole("button", { name: "Оставить своё" }));
  expect(textbox("summary").value).toBe("Still editing");
  expect(button("Save").disabled).toBe(false);
  const attempts = editor.calls.filter((call) => call.route === "/rebase");
  expect(attempts[0]?.headers.get("If-Match")).toBe('W/"v1"');
  expect(attempts[0]?.headers.get("Idempotency-Key")).toBeTruthy();
  expect(attempts[1]?.body).toEqual({ onto_revision_id: "r2",
    resolutions: [{ conflict_id: "title", keep: "theirs" }, { conflict_id: "collision", new_key: "P1.3" }] });
  expect(attempts[1]?.headers.get("Idempotency-Key")).not.toBe(attempts[0]?.headers.get("Idempotency-Key"));
});

it("shows the foreign save immediately and gates preview refresh until its snapshot arrives", async () => {
  let finish!: (response: Response) => void;
  const pending = new Promise<Response>((resolve) => { finish = resolve; });
  let waitForSnapshot = false;
  let preparations = 0;
  const editor = setup((call) => {
    if (!call.route && call.method === "GET" && waitForSnapshot) return pending;
    if (call.route === "/publication-preview") return preview(Number(call.body.expected_edit_version), ++preparations === 1 ? "one" : "two");
  }, { scoped: true });
  await screen.findByRole("heading", { name: "Delivery plan" });
  await waitFor(() => expect(editor.events).toEqual(["9", "9"]));
  await editor.user.click(button("Publish…"));
  await screen.findByText("pin-one");
  await editor.user.type(textbox("Причина публикации"), "Reviewed");
  waitForSnapshot = true;
  await act(async () => editor.send("draft-saved", { draft_id: "draft", edit_version: 2 }));
  await within(await screen.findByRole("dialog")).findByText("Предпросмотр устарел.");
  await screen.findByText("draft изменён другим пользователем.");
  expect(button("Publish shown changes").disabled).toBe(true);
  expect(button("Refresh preview").disabled).toBe(true);
  await editor.user.click(button("Refresh preview"));
  expect(preparations).toBe(1);
  expect(screen.getByText("pin-one")).toBeTruthy();
  await act(async () => finish(editor.snapshot(editor.draft)));
  expect(button("Refresh preview").disabled).toBe(true);
  expect(editor.calls.some((call) => call.route === "/validate" && call.body.expected_edit_version === 2)).toBe(false);
  waitForSnapshot = false;
  editor.draft.edit_version = 2;
  await waitFor(() => expect(button("Refresh preview").disabled).toBe(false), { timeout: 2500 });
  await editor.user.click(button("Refresh preview"));
  await screen.findByText("pin-two");
  expect(editor.calls.filter((call) => call.route === "/publication-preview").map((call) => call.body.expected_edit_version)).toEqual([1, 2]);
});
