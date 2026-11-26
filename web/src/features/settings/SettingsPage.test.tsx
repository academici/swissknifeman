// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { URL as FileURL } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { whoAmIKey } from "../../api/hooks/access";
import type { EntryView, ExplainReport, GetSchemaView, ImportConfig, ImportConfigResult } from "../../api/generated/settings";
import type { Uuid } from "../../api/generated/kernel";
import { keys } from "../../api/keys";
import { AuthProvider } from "../../app/providers/AuthProvider";
import { ScopeProvider } from "../../app/providers/ScopeProvider";
import { StreamProvider } from "../../app/providers/StreamProvider";
import { ToastProvider } from "../../app/providers/ToastProvider";
import { jsonEqual, own } from "../../components/schema-form/values";
import SettingsPage from "./SettingsPage";
import "../../../tests/setup";

type Section = GetSchemaView["sections"][number];
type Spec = Section["keys"][number];
const workspace = "0192f5c5-0b33-7c44-9a00-2b3c4d5e6f71" as Uuid;
const project = "0192f5c5-0b33-7c44-9a00-2b3c4d5e6f70" as Uuid;
const hostId = "0192f5c5-0b33-7c44-9a00-2b3c4d5e6f72" as Uuid;
const projectScope = `project:${project}`;
const workspaceScope = `workspace:${workspace}`;
const projectQueries = keys.forScope({ workspaceId: workspace, projectId: project });
const review = "execution.review.max_rounds";
const mode = "execution.workflow.profile";
const worker = "worker.capacity";
const taskWarn = "budgets.task.warn_tokens";
const taskMax = "budgets.task.max_tokens";
const runMax = "budgets.run.max_tokens";
const policy = "execution.work_policy.";
const secret = "fixtures.secret";
const unsafe = "fixtures.unsafe";
const append = "fixtures.list";
const hooks = "hooks.subscriptions";
const documentSchema = "urn:skm:settings:document:v1";
const malware = '<svg onload="attack()"><script>attack()</script></svg>\u202e';

function catalog(section: string, names: string[]): Section {
  const schema = JSON.parse(readFileSync(new FileURL(
    `../../../../src/skm/schemas/settings/${section}.v1.json`, import.meta.url,
  ), "utf8")) as Section["schema"];
  return {
    id: section, owner: section, title: section, schema_urn: String(schema.$id), schema,
    validators: [], keys: names.map((key) => {
      const value = key.split(".").slice(1).reduce<unknown>((value, part) => own(own(value, "properties"), part), schema);
      const { ui, ...metadata } = own(value, "x-skm") as Spec;
      const { write_permission: _permission, ...fields } = metadata as Spec & { write_permission?: string };
      void _permission; // GetSchemaView omits this field; it remains in the section schema.
      return { ...fields, key, section, value_schema: value as Spec["value_schema"],
        default: own(value, "default"), validators: [], ui: { ...ui, title: key } };
    }),
  };
}

const schema: GetSchemaView = {
  registry_digest: "registry",
  sections: [
    catalog("execution", [review, mode, ...["role_intensity", "verification_intensity", "role_warn_seconds", "repro_warn_seconds"]
      .map((name) => policy + name)]),
    catalog("budgets", [taskWarn, taskMax, runMax]),
    catalog("worker", [worker]),
    catalog("runtimes", ["enabled_runtimes", "enabled_models", "route_substitutions"].map(name => "runtimes.host." + name)),
    catalog("hooks", [hooks]),
    {
      id: "fixtures", owner: "fixtures", title: malware, schema_urn: "urn:fixtures", schema: {}, validators: [],
      keys: [secret, unsafe, append].map((key, index) => ({
        key, section: "fixtures", chain: "work", levels: ["project"], merge: "replace",
        reload: "live", override: true, sensitivity: key === secret ? "secret" : "public",
        portable: true, lockable: false, nullable: false, pack: false, confirm: key === unsafe,
        value_schema: key === append ? { type: "array", items: { type: "string" } } : { type: "string" },
        validators: [], default: key === secret ? "must-never-render" : key === append ? ["base"] : malware,
        ui: { group: "Fixtures", title: key, order: index, widget: "text",
          advanced: key === unsafe, help_url: "javascript:attack()" },
      })),
    },
  ],
};
const specs = schema.sections.flatMap(({ keys }) => keys);
type Write = { path: string; method: string; headers: Headers; body: Record<string, unknown> };

function backend({ live = false } = {}) {
  let generation = 1;
  let failWrite: "before" | "after" | undefined;
  let cursor = 10;
  let feed: ReadableStreamDefaultController<Uint8Array> | undefined;
  const subscriptions: string[] = [];
  let previewProblem: ImportConfigResult["problems"][number] | undefined;
  const rights: Record<string, string[]> = {
    instance: ["config.read", "config.write", "config.write_shared", "config.lock"],
    [workspace]: ["config.read", "config.write", "config.write_shared", "config.lock"],
    [project]: ["config.read", "config.write"],
  };
  const rows = new Map<string, Map<string, EntryView>>();
  const writes: Write[] = [];
  const historyReads: (string | null)[] = [];
  const receipts = new Map<string, Response>();
  const layer = (scope: string): EntryView["scope"] => {
    if (scope === "instance") return { level: "instance" };
    const [level, id] = scope.split(":");
    return { level: level as EntryView["scope"]["level"], scope_id: id as Uuid };
  };
  function entries(scope: string) {
    const found = rows.get(scope) ?? new Map();
    rows.set(scope, found);
    return found;
  }
  function save(scope: string, key: string, value: unknown, locked = false, op: EntryView["op"] = "set") {
    const previous = entries(scope).get(key);
    entries(scope).set(key, {
      entry_id: previous?.entry_id ?? crypto.randomUUID() as Uuid,
      scope: layer(scope), key, op, value, locked, row_version: (previous?.row_version ?? 0) + 1,
      updated_at: "2026-11-19T10:00:00Z" as EntryView["updated_at"], updated_by: project,
    });
    generation += 1;
  }
  function digest(scope: string) {
    return JSON.stringify([...entries(scope)].map(([key, { op, value, locked }]) => [key, op, value, locked]));
  }
  const chain = (scope: string) => scope === projectScope ? ["instance", workspaceScope, scope] :
    scope === "instance" ? [scope] : ["instance", scope];
  function effective(scope: string, spec: Spec, alternative?: { op: string; value?: unknown } | null) {
    const local = alternative === undefined ? entries(scope).get(spec.key) : alternative;
    const inherited = chain(scope).slice(0, -1).map((level) => entries(level).get(spec.key)).filter(
      (entry): entry is EntryView => !!entry,
    );
    const lock = inherited.find((entry) => entry.locked);
    const chosen = lock ?? local ?? inherited.at(-1);
    return chosen?.op === "unset" || !chosen ? spec.default : chosen.value;
  }
  function explain(scope: string): ExplainReport {
    return {
      schema: "urn:skm:config:explain:v1", scope: layer(scope), chain: chain(scope).map(layer), generation, digest: digest(scope),
      keys: specs.filter((spec) => spec.chain === (scope.startsWith("host:") ? "host" : "work")).map((spec) => {
        const stored = chain(scope).flatMap((level) => entries(level).get(spec.key) ?? []);
        const lock = stored.find((entry) => entry.locked);
        const winner = lock ?? stored.at(-1);
        const value = effective(scope, spec);
        const ref = (entry: EntryView) => ({ ...entry.scope, entry_id: entry.entry_id, row_version: entry.row_version });
        return {
          key: spec.key, present: value !== undefined, merge: spec.merge, reload: spec.reload, sensitivity: spec.sensitivity,
          value, winner: winner ? ref(winner) : { level: "default" },
          ...(lock ? { locked_by: ref(lock) } : {}),
          contributions: [
            { layer: { level: "default" }, op: "default", status: winner ? "shadowed" : "winner", value: spec.default },
            ...stored.map((entry) => ({
              layer: ref(entry), op: entry.op, status: entry === winner ? "winner" as const : "ignored" as const,
              value: entry.value, locked: entry.locked,
              ...(entry !== winner && lock ? { reason: "locked_above" as const } : {}),
            })),
          ],
          diagnostics: spec.key === unsafe ? [{ code: "NOTICE", severity: "info", message: malware }] : [],
        };
      }),
    };
  }
  const respond = (body: unknown) => Response.json(body);
  const conflict = (code = "VERSION_CONFLICT") => Response.json({
    code, category: "conflict", detail: "Changed by another tab",
  }, { status: 409, headers: { "Content-Type": "application/problem+json" } });

  function imported(scope: string, body: ImportConfig): Response {
    if (body.expected_entries_digest !== digest(scope)) return conflict();
    const doc: unknown = typeof body.document === "string" ? { budgets: { task: { warn_tokens: 90000 } } } : body.document;
    const permissions = rights[layer(scope).scope_id ?? "instance"] ?? [];
    if (Array.isArray(own(doc, "lock")) && !permissions.includes("config.lock")) {
      return Response.json({ code: "FORBIDDEN", category: "forbidden", detail: "Missing config.lock" }, {
        status: 403, headers: { "Content-Type": "application/problem+json" },
      });
    }
    const changes: ImportConfigResult["changes"][number][] = [];
    const effective_diff: ImportConfigResult["effective_diff"][number][] = [];
    const problems = previewProblem ? [previewProblem] : [];
    for (const spec of specs) {
      const { key } = spec;
      const before = entries(scope).get(key);
      const value = key.split(".").reduce<unknown>(own, doc);
      const appended = own(own(doc, "append"), key);
      const unset = own(doc, "unset");
      const locks = own(doc, "lock");
      const locked = Array.isArray(locks) && locks.includes(key);
      const after = Array.isArray(unset) && unset.includes(key) ? { op: "unset" as const, locked } :
        appended !== undefined ? { op: "append" as const, value: appended, locked } :
        value !== undefined ? { op: "set" as const, value, locked } :
        body.mode === "replace" ? null : undefined;
      if (after === undefined || (after === null && !before)) continue;
      if (before && after && jsonEqual(after, { op: before.op, value: before.value, locked: before.locked })) {
        changes.push({ key, before, after, change: "unchanged" });
        continue;
      }
      changes.push({ key, before: before ?? null, after, change: after === null ? "removed" : before ? "updated" : "added" });
      if (spec.confirm && !body.confirmed) problems.push({ key, code: "CONFIRMATION_REQUIRED", message: "Confirmation required" });
      const from = effective(scope, spec);
      const to = effective(scope, spec, after);
      if (!jsonEqual(from, to)) effective_diff.push({ key, before: from, after: to });
      if (!body.dry_run && !problems.length) {
        if (after === null) { entries(scope).delete(key); generation += 1; }
        else save(scope, key, "value" in after ? after.value : undefined, after.locked, after.op);
      }
    }
    return respond({
      dry_run: body.dry_run ?? false, applied: !body.dry_run && !problems.length, changes, effective_diff, problems,
      entries_digest_before: body.expected_entries_digest, entries_digest_after: digest(scope), generation,
    } satisfies ImportConfigResult);
  }

  vi.stubGlobal("fetch", vi.fn(async (input: string, init: RequestInit) => {
    const url = new URL(input, window.location.origin);
    const path = decodeURIComponent(url.pathname);
    const scope = url.searchParams.get("scope") ?? "instance";
    const method = init.method ?? "GET";
    if (path === "/api/v1/events" && live) {
      subscriptions.push(url.search);
      return new Response(new ReadableStream<Uint8Array>({
        start(controller) { feed = controller; },
      }), { headers: { "Content-Type": "text/event-stream" } });
    }
    if (path === "/api/v1/me") return respond({
      principal: { display_name: "Owner" }, effective_permissions: rights[url.searchParams.get("scope_id") ?? "instance"] ?? [],
      modules: {}, permissions_by_scope: rights, memberships: [], token: null,
    });
    if (path === "/api/v1/hosts") return respond({ items: [{
      host_id: hostId, name: "Сборочный хост", platform: { os: "linux", arch: "x86_64" }, state: "active",
    }], next: null });
    if (path === "/api/v1/config/schema") return respond(schema);
    if (path === "/api/v1/config/explain") return Response.json(explain(scope), {
      headers: live ? { "SKM-Events-Cursor": String(cursor) } : {},
    });
    if (path === "/api/v1/config/entries") return respond({ items: [...entries(scope).values()], next: null });
    if (path === "/api/v1/config/export") return respond({
      format: url.searchParams.get("format"), entries: [...entries(scope).values()], digest: digest(scope),
      document: url.searchParams.get("format") === "toml" ? "[budgets.task]\nwarn_tokens = 90000" : { schema: documentSchema },
    });
    if (path === "/api/v1/config/history") {
      const after = url.searchParams.get("after");
      historyReads.push(after);
      return respond({
        items: [{
          id: after ?? "first", change_kind: after ? "created" : "updated", actor_id: project, generation,
          key: url.searchParams.get("key"), changed_at: "2026-11-19", reason: malware,
          request_id: after ? "req-earlier" : "req-latest", old_op: null, new_op: "set", new_value: "history-value",
        }],
        next: after ? null : "opaque+cursor",
      });
    }
    if (path === "/api/v1/config/import" || path.startsWith("/api/v1/config/entries/")) {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      const headers = new Headers(init.headers);
      writes.push({ path, method, headers, body });
      const id = headers.get("Idempotency-Key");
      const replay = id && receipts.get(id);
      if (replay) return replay.clone();
      const failure = body.dry_run ? undefined : failWrite;
      if (failure) failWrite = undefined;
      if (failure === "before") throw new TypeError("Disconnected");
      const finishWrite = (result: Response) => {
        if (id && result.ok) receipts.set(id, result.clone());
        if (failure === "after") throw new TypeError("Disconnected");
        return result;
      };
      if (path.endsWith("/import")) {
        const dto = body as unknown as ImportConfig;
        const target = dto.scope.level === "instance" ? "instance" : `${dto.scope.level}:${dto.scope.scope_id}`;
        return finishWrite(imported(target, dto));
      }
      const [target = "", key = "", action] = path.slice("/api/v1/config/entries/".length).split("/");
      const row = entries(target).get(key);
      if (headers.get("If-None-Match") === "*" ? row : headers.get("If-Match") !== `W/"v${row?.row_version}"`) {
        return conflict(headers.get("If-None-Match") ? "ALREADY_EXISTS" : undefined);
      }
      if (method === "DELETE") { entries(target).delete(key); generation += 1; }
      else if (action === "lock" || action === "unlock") save(target, key, row?.value, action === "lock", row?.op);
      else save(target, key, body.value, row?.locked, action === "unset" ? "unset" : body.mode === "append" ? "append" : "set");
      return finishWrite(respond({ entry: entries(target).get(key), generation }));
    }
    throw new Error(`Unexpected request ${method} ${path}`);
  }));
  return {
    rights, writes, historyReads, save, entries, subscriptions,
    changed(scope: string, key: string) {
      cursor += 1;
      const event = { type: "urn:skm:settings:event:ConfigChanged:v1", stream_kind: "workspace",
        workspace_id: workspace, stream_id: workspace, payload: { scope: layer(scope), keys: [key] } };
      if (!feed) throw new Error("Settings did not subscribe");
      feed.enqueue(new TextEncoder().encode(`id: ${cursor}\nevent: ConfigChanged\ndata: ${JSON.stringify(event)}\n\n`));
    },
    disconnectWrite: (when: NonNullable<typeof failWrite>) => { failWrite = when; },
    rejectPreview: (problem: typeof previewProblem) => { previewProblem = problem; },
  };
}

function open(scope = projectScope) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const view = render(<MemoryRouter initialEntries={[`/settings?scope=${scope}`]}>
    <QueryClientProvider client={client}>
      <AuthProvider initialToken="owner">
        <ScopeProvider>
          <ToastProvider><StreamProvider><SettingsPage /></StreamProvider></ToastProvider>
        </ScopeProvider>
      </AuthProvider>
    </QueryClientProvider>
  </MemoryRouter>);
  return { root: within(view.container), client };
}

async function setting(name: string, root: ReturnType<typeof within> = screen, section?: string | RegExp) {
  if (section) {
    const select = within(await root.findByRole("navigation", { name: "Разделы настроек" }));
    fireEvent.click(select.getByRole("button", { name: section }));
  }
  return within(await root.findByRole("article", { name }));
}

async function preview(root: ReturnType<typeof within> = screen) {
  fireEvent.click(root.getByRole("button", { name: "Предпросмотр" }));
  return within(await screen.findByRole("dialog", { name: /^Предпросмотр/ }));
}

async function apply(dialog: ReturnType<typeof within>) {
  const button = await dialog.findByRole("button", { name: "Применить" });
  expect(button).toHaveProperty("disabled", false);
  fireEvent.click(button);
}

async function startImport(document: object, mode: "merge" | "replace" = "merge") {
  fireEvent.click(await screen.findByRole("button", { name: "Импорт" }));
  const importer = within(await screen.findByRole("dialog", { name: "Импорт настроек" }));
  fireEvent.change(importer.getByRole("combobox", { name: "Формат" }), { target: { value: "json" } });
  fireEvent.change(importer.getByRole("combobox", { name: "Режим" }), { target: { value: mode } });
  fireEvent.change(importer.getByRole("textbox", { name: "Документ" }), { target: { value: JSON.stringify(document) } });
  return preview(importer);
}

async function saveRow(row: ReturnType<typeof within>) {
  fireEvent.click(await row.findByRole("button", { name: "Сохранить только этот ключ" }));
  const dialog = within(await screen.findByRole("dialog", { name: /Сохранить ключ/ }));
  fireEvent.click(dialog.getByRole("button", { name: "Сохранить ключ" }));
  return dialog;
}

describe("SettingsPage", () => {
  it("previews and applies the same document, retrying a lost response with the same key and reason", async () => {
    const api = backend();
    api.disconnectWrite("after");
    const tab = open();
    const row = await setting(review);
    fireEvent.change(row.getByRole("spinbutton", { name: review }), { target: { value: "1" } });
    const dialog = await preview();
    await dialog.findByRole("heading", { name: "Эффективные значения" });
    fireEvent.change(dialog.getByRole("textbox", { name: "Причина" }), { target: { value: "Review budget" } });
    await apply(dialog);
    await dialog.findByRole("button", { name: "Повторить применение" });
    expect(api.entries(projectScope).get(review)?.value).toBe(1);
    await tab.client.invalidateQueries({
      queryKey: projectQueries.configExplain(projectScope),
    });
    fireEvent.click(dialog.getByRole("button", { name: "Повторить применение" }));
    await screen.findByText("Настройки сохранены.");
    const [dry, first, retried] = api.writes;
    expect(dry?.body).toMatchObject({ dry_run: true, scope: { level: "project", scope_id: project },
      document: { schema: documentSchema, execution: { review: { max_rounds: 1 } } } });
    expect(first?.body).toMatchObject({ dry_run: false, document: dry?.body.document,
      expected_entries_digest: dry?.body.expected_entries_digest, reason: "Review budget" });
    expect(first?.headers.get("Idempotency-Key")).toMatch(/^web-[0-9a-f-]{36}$/);
    expect(retried?.headers.get("Idempotency-Key")).toBe(first?.headers.get("Idempotency-Key"));
    expect(retried?.body).toEqual(first?.body);
    expect(screen.queryByRole("region", { name: "Черновик" })).toBeNull();
  });

  it("rebases a real two-tab 409 only after choosing which version to keep", async () => {
    const api = backend();
    api.save(projectScope, review, 4);
    const a = open();
    const b = open();
    const rowA = await setting(review, a.root);
    const rowB = await setting(review, b.root);
    fireEvent.change(rowA.getByRole("spinbutton", { name: review }), { target: { value: "2" } });
    fireEvent.change(rowB.getByRole("spinbutton", { name: review }), { target: { value: "3" } });
    await apply(await preview(a.root));
    await a.root.findByText("Настройки сохранены.");
    fireEvent.click(await rowB.findByRole("button", { name: "Сохранить только этот ключ" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: /Сохранить ключ/ }))
      .getByRole("button", { name: "Сохранить ключ" }));
    const conflict = within(await screen.findByRole("dialog", { name: "Конфликт изменений" }));
    expect(conflict.getByRole("columnheader", { name: "Base" })).toBeTruthy();
    expect(await conflict.findByRole("cell", { name: /v2 2/ })).toBeTruthy();
    expect(conflict.getByRole("columnheader", { name: "Yours" })).toBeTruthy();
    const rebase = conflict.getByRole("button", { name: "Rebase draft" });
    expect(rebase).toHaveProperty("disabled", true);
    fireEvent.click(conflict.getByRole("button", { name: `Take mine · ${review}` }));
    fireEvent.click(rebase);
    expect(api.writes.at(-1)?.headers.get("If-Match")).toBe('W/"v1"');
    expect(api.entries(projectScope).get(review)?.value).toBe(2);
    fireEvent.click(await rowB.findByRole("button", { name: "Сохранить только этот ключ" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: /Сохранить ключ/ }))
      .getByRole("button", { name: "Сохранить ключ" }));
    await b.root.findByText("Настройки сохранены.");
    expect(api.writes.at(-1)?.headers.get("If-Match")).toBe('W/"v2"');
    expect(api.entries(projectScope).get(review)?.value).toBe(3);
  });

  it("uses the preview digest for apply and re-previews after an import CAS conflict", async () => {
    const api = backend();
    api.save(projectScope, review, 4);
    open();
    const row = await setting(review);
    fireEvent.change(row.getByRole("spinbutton", { name: review }), { target: { value: "2" } });
    const dialog = await preview();
    await dialog.findByRole("heading", { name: "Изменения записей" });
    api.save(projectScope, review, 3);
    await apply(dialog);
    const conflict = within(await screen.findByRole("dialog", { name: "Конфликт изменений" }));
    expect(await conflict.findByRole("cell", { name: /v2 3/ })).toBeTruthy();
    expect(api.writes).toHaveLength(2);
    expect(api.writes[1]?.body.expected_entries_digest).toBe(api.writes[0]?.body.expected_entries_digest);
    fireEvent.click(conflict.getByRole("button", { name: `Take mine · ${review}` }));
    fireEvent.click(conflict.getByRole("button", { name: "Rebase draft" }));
    const next = await preview();
    await next.findByRole("heading", { name: "Изменения записей" });
    expect(api.writes.at(-1)?.body.expected_entries_digest).not.toBe(api.writes[0]?.body.expected_entries_digest);
    await apply(next);
    await screen.findByText("Настройки сохранены.");
    expect(api.entries(projectScope).get(review)?.value).toBe(2);
  });

  it("distinguishes create-only unset, removal, and inherited values", async () => {
    const api = backend();
    api.save(workspaceScope, mode, "tight-review");
    open();
    const row = await setting(mode);
    expect(row.getAllByText('"tight-review"').length).toBeGreaterThan(0);
    fireEvent.click(row.getByRole("button", { name: "Сбросить к умолчанию" }));
    fireEvent.click(row.getByRole("button", { name: "Сохранить только этот ключ" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: /Сохранить ключ/ }))
      .getByRole("button", { name: "Сохранить ключ" }));
    await waitFor(() => expect(row.getByRole("button", { name: "Убрать запись" })).toBeTruthy());
    expect(api.writes.at(-1)?.path).toMatch(/\/unset$/);
    expect(api.writes.at(-1)?.headers.get("If-None-Match")).toBe("*");
    expect(row.getAllByText(JSON.stringify(specs.find(({ key }) => key === mode)?.default)).length).toBeGreaterThan(0);
    fireEvent.click(row.getByRole("button", { name: "Убрать запись" }));
    fireEvent.click(row.getByRole("button", { name: "Сохранить только этот ключ" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: /Сохранить ключ/ }))
      .getByRole("button", { name: "Сохранить ключ" }));
    expect((await row.findAllByText('"tight-review"')).length).toBeGreaterThan(0);
    expect(api.writes.at(-1)?.method).toBe("DELETE");
    expect(api.writes.at(-1)?.headers.get("If-Match")).toBe('W/"v1"');
  });

  it("opens host settings from the host dropdown", async () => {
    backend();
    open();
    await setting(review);
    await waitFor(() => expect(screen.getByLabelText("Уровень записи")).toHaveProperty("disabled", false));
    fireEvent.change(screen.getByLabelText("Уровень записи"), { target: { value: "host" } });
    await screen.findByRole("option", { name: /Сборочный хост/ });
    fireEvent.change(screen.getByLabelText("Хост"), { target: { value: hostId } });
    expect(await screen.findByText(`host:${hostId}`, { selector: "p code" })).toBeTruthy();
    for (const name of ["enabled_runtimes", "enabled_models", "route_substitutions"]) {
      expect(await setting(`runtimes.host.${name}`, screen, /runtimes/)).toBeTruthy();
    }
    expect(screen.getByLabelText("Хост")).toHaveProperty("value", hostId);
  });

  it("uses the typed work-policy and budget catalog, with host restrictions and lock provenance", async () => {
    const api = backend();
    api.save(workspaceScope, policy + "verification_intensity", "heavy", true);
    api.save(projectScope, taskWarn, 80000);
    open();
    const role = await setting(policy + "role_intensity");
    expect(role.getAllByText("medium", { exact: true }).length).toBeGreaterThan(0);
    const verification = await setting(policy + "verification_intensity");
    expect(verification.getByText(/Заблокировано на workspace/)).toBeTruthy();
    expect(verification.queryByRole("button", { name: "Сбросить к умолчанию" })).toBeNull();
    const warnings = await setting(policy + "role_warn_seconds");
    expect(warnings.getAllByRole("spinbutton").map((input) => Number((input as HTMLInputElement).value))).toContain(1800);
    const repro = await setting(policy + "repro_warn_seconds");
    expect(repro.getByRole("spinbutton", { name: "medium" })).toHaveProperty("value", "60");
    const host = await setting(worker, screen, /worker \(H\)/u);
    expect(host.getByRole("spinbutton", { name: worker })).toHaveProperty("readOnly", true);
    expect(host.getByRole("link", { name: "Перейти на instance" }).getAttribute("href")).toBe("/settings?scope=instance");
    const warning = await setting(taskWarn, screen, "budgets");
    expect(warning.getByRole("spinbutton", { name: taskWarn })).toHaveProperty("value", "80000");
    const task = await setting(taskMax);
    expect(task.getByRole("spinbutton", { name: taskMax })).toHaveProperty("value", "0");
    expect(task.queryByRole("button", { name: "Сбросить к умолчанию" })).toBeNull();
    const run = await setting(runMax);
    expect(run.getByRole("spinbutton", { name: runMax })).toHaveProperty("value", "0");
    fireEvent.click(warning.getByRole("button", { name: "Убрать запись" }));
    const dialog = await preview();
    expect(await dialog.findByRole("cell", { name: "100000" })).toBeTruthy();
    await apply(dialog);
    await waitFor(() => expect(warning.getByRole("spinbutton", { name: taskWarn })).toHaveProperty("value", "100000"));
    expect(api.writes.at(-1)?.body).toMatchObject({ mode: "replace", dry_run: false });
  });

  it("previews, applies and removes a typed work-policy override to resume inheritance", async () => {
    const api = backend();
    const key = policy + "repro_warn_seconds";
    const inherited = { light: 30, medium: 65, heavy: 90 };
    api.save(workspaceScope, key, inherited);
    open();
    const row = await setting(key);
    expect(row.getByRole("spinbutton", { name: "medium" })).toHaveProperty("value", "65");
    fireEvent.change(row.getByRole("spinbutton", { name: "medium" }), { target: { value: "75" } });
    const dialog = await preview();
    const override = { ...inherited, medium: 75 };
    const expected = { execution: { work_policy: { repro_warn_seconds: override } } };
    await dialog.findByRole("heading", { name: "Эффективные значения" });
    expect(api.writes.at(-1)?.body).toMatchObject({ dry_run: true, document: expected });
    await apply(dialog);
    await row.findByRole("button", { name: "Убрать запись" });
    expect(api.writes.at(-1)?.body).toMatchObject({ dry_run: false, document: expected });
    expect(api.entries(projectScope).get(key)?.value).toEqual(override);
    fireEvent.click(row.getByRole("button", { name: "Убрать запись" }));
    const reset = await preview();
    expect(await reset.findByRole("cell", { name: "removed" })).toBeTruthy();
    await apply(reset);
    await waitFor(() => expect(row.getByRole("spinbutton", { name: "medium" })).toHaveProperty("value", "65"));
    expect(api.entries(projectScope).has(key)).toBe(false);
    expect(row.getByText(`workspace · ${workspace} (v1)`)).toBeTruthy();
  });

  it("shows explicit owner hard-budget ceilings and their lock provenance", async () => {
    const api = backend();
    api.save("instance", taskMax, 150000, true);
    api.save("instance", runMax, 750000, true);
    open();
    const task = await setting(taskMax, screen, "budgets 🔒");
    expect(task.getByRole("spinbutton", { name: taskMax })).toHaveProperty("value", "150000");
    expect(task.getByText(/Заблокировано на instance/)).toBeTruthy();
    const run = await setting(runMax);
    expect(run.getByRole("spinbutton", { name: runMax })).toHaveProperty("value", "750000");
    expect(run.getByText(/Заблокировано на instance/)).toBeTruthy();
  });

  it("requires scoped write, per-key permission and lock permission, then sends the version and reason", async () => {
    const api = backend();
    api.rights[project] = ["config.read", "config.write_shared"];
    api.rights[workspace] = ["config.read", "config.write_shared", "config.lock"];
    api.save("instance", review, 2);
    api.save(workspaceScope, review, 2);
    const tab = open();
    const row = await setting(review);
    expect(row.getByRole("spinbutton", { name: review })).toHaveProperty("readOnly", true);
    expect(tab.root.queryByRole("button", { name: "Импорт" })).toBeNull();
    fireEvent.change(tab.root.getByRole("combobox", { name: "Уровень записи" }), { target: { value: "workspace" } });
    const workspaceRow = await setting(review);
    expect(workspaceRow.getByRole("spinbutton", { name: review })).toHaveProperty("readOnly", true);
    expect(workspaceRow.queryByRole("button", { name: "Заблокировать" })).toBeNull();
    expect(tab.root.queryByRole("button", { name: "Импорт" })).toBeNull();
    fireEvent.change(tab.root.getByRole("combobox", { name: "Уровень записи" }), { target: { value: "instance" } });
    const instanceRow = await setting(review);
    fireEvent.click(instanceRow.getByRole("button", { name: "Заблокировать" }));
    const lock = within(await screen.findByRole("dialog", { name: /Заблокировать/ }));
    const commit = lock.getByRole("button", { name: "Заблокировать" });
    expect(commit).toHaveProperty("disabled", true);
    fireEvent.change(lock.getByRole("textbox", { name: "Причина" }), { target: { value: "Owner ceiling" } });
    fireEvent.click(commit);
    const unlock = await instanceRow.findByRole("button", { name: "Разблокировать" });
    expect(api.writes.at(-1)?.headers.get("If-Match")).toBe('W/"v1"');
    expect(api.writes.at(-1)?.body.reason).toBe("Owner ceiling");
    fireEvent.click(unlock);
    const unlockDialog = within(await screen.findByRole("dialog", { name: /Разблокировать/ }));
    fireEvent.change(unlockDialog.getByRole("textbox", { name: "Причина" }), { target: { value: "Remove ceiling" } });
    fireEvent.click(unlockDialog.getByRole("button", { name: "Разблокировать" }));
    await instanceRow.findByRole("button", { name: "Заблокировать" });
    expect(api.writes.at(-1)?.headers.get("If-Match")).toBe('W/"v2"');
    expect(api.writes.at(-1)?.body.reason).toBe("Remove ceiling");
    const hook = await setting(hooks, screen, "hooks");
    expect(hook.queryByRole("button", { name: "Сбросить к умолчанию" })).toBeNull();
  });

  it("accepts only secret references, paginates history and safely renders confirmation, provenance and previews", async () => {
    const api = backend();
    const tab = open();
    const search = await tab.root.findByRole("searchbox", { name: "Поиск настроек" });
    fireEvent.change(search, { target: { value: "fixtures" } });
    const secretRow = await setting(secret);
    const field = secretRow.getByLabelText(secret) as HTMLInputElement;
    expect(field.type).toBe("password");
    expect(field.value).toBe("");
    fireEvent.change(field, { target: { value: "raw-secret" } });
    expect(field.value).toBe("");
    expect(screen.queryByRole("region", { name: "Черновик" })).toBeNull();
    fireEvent.change(field, { target: { value: "secret://env/API_TOKEN" } });
    const unsafeRow = await setting(unsafe);
    fireEvent.change(unsafeRow.getByRole("textbox", { name: unsafe }), { target: { value: malware + " edited" } });
    expect(document.querySelector("svg[onload], script, a[href^='javascript:']")).toBeNull();
    expect(document.body.textContent).not.toContain("must-never-render");
    expect(tab.root.getByRole("button", { name: /\\u202e/ })).toBeTruthy();
    const dialog = await preview(tab.root);
    const confirm = await dialog.findByRole("checkbox", { name: /Подтверждаю изменение параметров/ });
    expect(dialog.getByRole("button", { name: "Применить" })).toHaveProperty("disabled", true);
    expect(dialog.getAllByText(/<svg onload=/u).length).toBeGreaterThan(0);
    expect(document.querySelector("svg[onload], script, a[href^='javascript:']")).toBeNull();
    fireEvent.click(confirm);
    await apply(dialog);
    await tab.root.findByText("Настройки сохранены.");
    expect(api.writes.at(-1)?.body).toMatchObject({
      confirmed: true, document: { fixtures: { secret: "secret://env/API_TOKEN" } },
    });
    fireEvent.click(unsafeRow.getByRole("button", { name: `История · ${unsafe}` }));
    const history = within(await screen.findByRole("dialog", { name: `История · ${unsafe}` }));
    expect(await history.findByText("req-latest")).toBeTruthy();
    fireEvent.click(history.getByRole("button", { name: "Загрузить ещё" }));
    expect(await history.findByText("req-earlier")).toBeTruthy();
    expect(api.historyReads).toEqual([null, "opaque+cursor"]);
    expect(document.querySelector("svg[onload], script")).toBeNull();
  });

  it("blocks a rejected preview, observes version drift and takes the current row", async () => {
    const api = backend();
    api.save(projectScope, review, 4);
    api.rejectPreview({ key: review, code: "CONFIG_INVALID", message: malware });
    const tab = open();
    const row = await setting(review);
    fireEvent.change(row.getByRole("spinbutton", { name: review }), { target: { value: "2" } });
    const dialog = await preview();
    expect(await dialog.findByRole("alert", { name: "Ошибки предпросмотра" })).toBeTruthy();
    expect(dialog.getByRole("button", { name: "Применить" })).toHaveProperty("disabled", true);
    api.save(projectScope, review, 3);
    await tab.client.invalidateQueries({ queryKey: projectQueries.configExplain(projectScope) });
    const conflict = within(await screen.findByRole("dialog", { name: "Конфликт изменений" }));
    fireEvent.click(conflict.getByRole("button", { name: `Take current · ${review}` }));
    fireEvent.click(conflict.getByRole("button", { name: "Rebase draft" }));
    expect(row.getByRole("spinbutton", { name: review })).toHaveProperty("value", "3");
    expect(tab.root.queryByRole("region", { name: "Черновик" })).toBeNull();
    expect(api.writes).toHaveLength(1);
  });

  it("imports TOML in merge mode and JSON in replace mode, and downloads export as an attachment", async () => {
    const api = backend();
    open();
    await setting(review);
    fireEvent.click(screen.getByRole("button", { name: "Импорт" }));
    let importer = within(await screen.findByRole("dialog", { name: "Импорт настроек" }));
    const toml = "[budgets.task]\nwarn_tokens = 90000";
    fireEvent.change(importer.getByRole("textbox", { name: "Документ" }), { target: { value: toml } });
    const tomlPreview = await preview(importer);
    await tomlPreview.findByRole("heading", { name: "Изменения записей" });
    await apply(tomlPreview);
    await screen.findByText("Настройки сохранены.");
    expect(api.writes.at(-1)?.body).toMatchObject({ format: "toml", document: toml, mode: "merge", dry_run: false });
    await waitFor(() => expect(screen.getByRole("button", { name: "Импорт" })).toHaveProperty("disabled", false));
    fireEvent.click(screen.getByRole("button", { name: "Импорт" }));
    importer = within(await screen.findByRole("dialog", { name: "Импорт настроек" }));
    fireEvent.change(importer.getByRole("combobox", { name: "Формат" }), { target: { value: "json" } });
    fireEvent.change(importer.getByRole("combobox", { name: "Режим" }), { target: { value: "replace" } });
    const doc = { schema: documentSchema, execution: { review: { max_rounds: 2 } } };
    fireEvent.change(importer.getByRole("textbox", { name: "Документ" }), { target: { value: JSON.stringify(doc) } });
    const jsonPreview = await preview(importer);
    await jsonPreview.findByRole("cell", { name: "removed" });
    await apply(jsonPreview);
    await waitFor(() => expect(api.entries(projectScope).get(review)?.value).toBe(2));
    expect(api.writes.at(-1)?.body).toMatchObject({ format: "json", document: doc, mode: "replace", dry_run: false });

    const create = vi.fn(() => "blob:settings");
    const revoke = vi.fn();
    const objectUrl = class extends URL {
      static createObjectURL = create;
      static revokeObjectURL = revoke;
    };
    vi.stubGlobal("URL", objectUrl);
    const download = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe("settings.toml");
      expect(this.href).toBe("blob:settings");
    });
    fireEvent.click(screen.getByRole("button", { name: "Экспорт" }));
    await waitFor(() => expect(download).toHaveBeenCalledOnce());
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ type: "application/toml" }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:settings"));
  });

  it("stages an append and creates the row only if it still does not exist", async () => {
    const api = backend();
    open();
    fireEvent.change(await screen.findByRole("searchbox", { name: "Поиск настроек" }), { target: { value: append } });
    const row = await setting(append);
    fireEvent.click(row.getByRole("button", { name: "Добавить к наследуемому списку" }));
    const dialog = await preview();
    await dialog.findByRole("heading", { name: "Изменения записей" });
    expect(api.writes.at(-1)?.body.document).toMatchObject({ append: { [append]: [] } });
    fireEvent.click(dialog.getByRole("button", { name: "Закрыть" }));
    fireEvent.click(row.getByRole("button", { name: "Сохранить только этот ключ" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: /Сохранить ключ/ }))
      .getByRole("button", { name: "Сохранить ключ" }));
    await screen.findByText("Настройки сохранены.");
    expect(api.writes.at(-1)?.headers.get("If-None-Match")).toBe("*");
    expect(api.writes.at(-1)?.body).toMatchObject({ mode: "append", value: [] });
  });

  it("opens ConflictView when a create-only row write returns ALREADY_EXISTS", async () => {
    const api = backend();
    open();
    const row = await setting(review);
    fireEvent.change(row.getByRole("spinbutton", { name: review }), { target: { value: "1" } });
    api.save(projectScope, review, 3);
    await saveRow(row);
    const comparison = within(await screen.findByRole("row", { name: new RegExp(review) }));
    const conflict = within(screen.getByRole("dialog", { name: "Конфликт изменений" }));
    expect(comparison.getByRole("cell", { name: "Нет записи" })).toBeTruthy();
    expect(comparison.getByRole("cell", { name: /v1 3/ })).toBeTruthy();
    expect(comparison.getByRole("cell", { name: "set 1" })).toBeTruthy();
    expect(api.writes.at(-1)?.headers.get("If-None-Match")).toBe("*");
    fireEvent.click(conflict.getByRole("button", { name: `Take current · ${review}` }));
    fireEvent.click(conflict.getByRole("button", { name: "Rebase draft" }));
    expect(row.getByRole("spinbutton", { name: review })).toHaveProperty("value", "3");
  });

  it("removes a key via CAS without requesting permission on an unrelated locked row", async () => {
    const api = backend();
    api.rights[workspace] = ["config.read", "config.write", "config.write_shared"];
    api.save(workspaceScope, policy + "verification_intensity", "heavy", true);
    api.save(workspaceScope, review, 3);
    open(workspaceScope);
    const remove = await setting(review);
    fireEvent.click(remove.getByRole("button", { name: "Убрать запись" }));
    const profile = await setting(mode);
    fireEvent.change(profile.getByRole("textbox", { name: mode }), { target: { value: "tight-review" } });
    expect(screen.getByRole("button", { name: "Предпросмотр" })).toHaveProperty("disabled", true);
    await saveRow(remove);
    await waitFor(() => expect(screen.getByRole("button", { name: "Предпросмотр" })).toHaveProperty("disabled", false));
    expect(api.writes).toHaveLength(1);
    expect(api.writes[0]).toMatchObject({ method: "DELETE", path: `/api/v1/config/entries/${workspaceScope}/${review}` });
    expect(api.writes[0]?.headers.get("If-Match")).toBe('W/"v1"');
    expect(api.entries(workspaceScope).has(review)).toBe(false);
    expect(api.entries(workspaceScope).get(policy + "verification_intensity")?.locked).toBe(true);
    expect(profile.getByRole("textbox", { name: mode })).toHaveProperty("value", "tight-review");
    const dialog = await preview();
    await dialog.findByRole("heading", { name: "Изменения записей" });
    expect(api.writes.at(-1)?.body).toMatchObject({
      dry_run: true, mode: "merge", document: { execution: { workflow: { profile: "tight-review" } } },
    });
    await apply(dialog);
    await waitFor(() => expect(api.entries(workspaceScope).get(mode)?.value).toBe("tight-review"));
  });

  it.each(["apply CAS", "refresh", "dry-run CAS"] as const)("rebases a file import after %s and runs a fresh preview", async (drift) => {
    const api = backend();
    api.save(projectScope, review, 4);
    api.save(projectScope, taskWarn, 80000);
    const tab = open();
    await setting(review);
    const change = () => {
      api.save(projectScope, review, 3);
      api.save(projectScope, taskWarn, 85000);
      api.save(projectScope, mode, "tight-review");
    };
    if (drift === "dry-run CAS") change();
    const dialog = await startImport({
      schema: documentSchema, execution: { review: { max_rounds: 2 } }, budgets: { task: { warn_tokens: 90000 } },
    }, "replace");
    if (drift !== "dry-run CAS") {
      await dialog.findByRole("heading", { name: "Изменения записей" });
      change();
      if (drift === "apply CAS") await apply(dialog);
      else await tab.client.invalidateQueries({ queryKey: projectQueries.configExplain(projectScope) });
    }
    const comparison = within(await screen.findByRole("row", { name: new RegExp(review) }));
    const conflict = within(screen.getByRole("dialog", { name: "Конфликт изменений" }));
    expect(comparison.getByRole("cell", { name: /v1 4/ })).toBeTruthy();
    expect(comparison.getByRole("cell", { name: /v2 3/ })).toBeTruthy();
    expect(comparison.getByRole("cell", { name: "set 2" })).toBeTruthy();
    const rebase = conflict.getByRole("button", { name: "Rebase draft" });
    fireEvent.click(conflict.getByRole("button", { name: `Take mine · ${review}` }));
    expect(rebase).toHaveProperty("disabled", true);
    fireEvent.click(conflict.getByRole("button", { name: `Take current · ${taskWarn}` }));
    await waitFor(() => expect(rebase).toHaveProperty("disabled", false));
    fireEvent.click(rebase);
    const next = within(await screen.findByRole("dialog", { name: /^Предпросмотр/ }));
    await next.findByRole("heading", { name: "Изменения записей" });
    const rebased = api.writes.at(-1)?.body;
    expect(rebased).toMatchObject({
      dry_run: true, mode: "merge", document: { schema: documentSchema, execution: { review: { max_rounds: 2 } } },
    });
    expect(rebased?.expected_entries_digest).not.toBe(api.writes[0]?.body.expected_entries_digest);
    expect(api.entries(projectScope).get(review)?.value).toBe(3);
    await apply(next);
    await screen.findByText("Настройки сохранены.");
    expect(api.entries(projectScope).get(review)?.value).toBe(2);
    expect(api.entries(projectScope).get(taskWarn)?.value).toBe(85000);
    expect(api.entries(projectScope).get(mode)?.value).toBe("tight-review");
  });

  it("retries an import receipt from ConflictView with the original key and body", async () => {
    const api = backend();
    api.disconnectWrite("after");
    const tab = open();
    await setting(review);
    const dialog = await startImport({ execution: { review: { max_rounds: 1 } } });
    await apply(dialog);
    await dialog.findByRole("button", { name: "Повторить применение" });
    await tab.client.invalidateQueries({ queryKey: projectQueries.configExplain(projectScope) });
    const retry = await screen.findByRole("button", { name: "Повторить исходный запрос" });
    expect(screen.getByRole("columnheader", { name: "Current" })).toBeTruthy();
    fireEvent.click(retry);
    await screen.findByText("Настройки сохранены.");
    expect(api.writes).toHaveLength(3);
    expect(api.writes[2]?.headers.get("Idempotency-Key")).toBe(api.writes[1]?.headers.get("Idempotency-Key"));
    expect(api.writes[2]?.body).toEqual(api.writes[1]?.body);
  });

  it("blocks an apply retry after inherited drift with the same target digest", async () => {
    const api = backend();
    api.disconnectWrite("before");
    const tab = open();
    const row = await setting(review);
    fireEvent.change(row.getByRole("spinbutton", { name: review }), { target: { value: "1" } });
    const dialog = await preview();
    await apply(dialog);
    const retry = await dialog.findByRole("button", { name: "Повторить применение" });
    expect(retry).toHaveProperty("disabled", false);
    api.save(workspaceScope, review, 3);
    await tab.client.invalidateQueries({ queryKey: projectQueries.configExplain(projectScope) });
    await dialog.findByText(/Предпросмотр устарел/);
    expect(retry).toHaveProperty("disabled", true);
    expect(api.writes).toHaveLength(2);
    expect(api.entries(projectScope).has(review)).toBe(false);
  });

  it.each(["inherited drift", "revoked permission"] as const)("blocks a row retry after %s", async (change) => {
    const api = backend();
    api.disconnectWrite("before");
    const tab = open();
    const row = await setting(review);
    fireEvent.change(row.getByRole("spinbutton", { name: review }), { target: { value: "1" } });
    const dialog = await saveRow(row);
    await dialog.findByRole("button", { name: "Повторить" });
    if (change === "inherited drift") {
      api.save(workspaceScope, review, 3);
      await tab.client.invalidateQueries({ queryKey: projectQueries.configExplain(projectScope) });
    } else {
      api.rights[project] = ["config.read"];
      await tab.client.invalidateQueries({ queryKey: whoAmIKey });
    }
    await waitFor(() => expect(dialog.queryByRole("button", { name: "Повторить" })).toBeNull());
    expect(api.writes).toHaveLength(1);
    expect(api.entries(projectScope).has(review)).toBe(false);
  });

  it("detects a recreated row even when its version and the entries digest match the draft", async () => {
    const api = backend();
    api.save(projectScope, review, 4);
    const tab = open();
    const row = await setting(review);
    fireEvent.change(row.getByRole("spinbutton", { name: review }), { target: { value: "1" } });
    api.entries(projectScope).delete(review);
    api.save(projectScope, review, 4);
    await tab.client.invalidateQueries({ queryKey: projectQueries.configExplain(projectScope) });
    const conflict = within(await screen.findByRole("dialog", { name: "Конфликт изменений" }));
    expect(conflict.getAllByRole("cell", { name: /v1 4/ })).toHaveLength(2);
    expect(conflict.getByRole("button", { name: "Rebase draft" })).toHaveProperty("disabled", true);
    expect(api.writes).toHaveLength(0);
  });

  it("subscribes from the explain cursor on a direct project link and refreshes rows and history", async () => {
    const api = backend({ live: true });
    api.save(projectScope, review, 4);
    const tab = open();
    const row = await setting(review);
    expect(row.getByRole("spinbutton", { name: review })).toHaveProperty("value", "4");
    expect(api.subscriptions.map((query) => Object.fromEntries(new URLSearchParams(query)))).toEqual([
      { workspace_id: workspace, after: "10" },
    ]);
    expect(tab.client.getQueryData(projectQueries.configExplain(projectScope))).toBeDefined();
    fireEvent.click(row.getByRole("button", { name: `История · ${review}` }));
    const history = within(await screen.findByRole("dialog", { name: `История · ${review}` }));
    await history.findByText("req-latest");
    api.save(projectScope, review, 3);
    api.changed(projectScope, review);
    await waitFor(() => expect(row.getByLabelText(review)).toHaveProperty("value", "3"));
    await waitFor(() => expect(api.historyReads).toEqual([null, null]));
    expect(tab.client.getQueryData(projectQueries.configHistory(projectScope, review))).toBeDefined();
  });
});
