// @vitest-environment jsdom
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";
import { App } from "../../app/App";
import type { Uuid } from "../../api/generated/kernel";

const workspace = "0192f5c5-0b33-7c44-9a00-2b3c4d5e6f70";
const project = "0192f5c5-0b33-7c44-9a00-2b3c4d5e6f71";
const run = "0192f5c7-2100-7b00-8000-b4c5d6e7f809";
const task = "0192f5c7-2110-7b10-8000-b4c5d6e7f810";
const finding = "0192f5c7-2110-7b10-8000-b4c5d6e7f811";
const permissions = ["inbox.read", "inbox.answer", "check.verdict", "run.control", "deviation.accept", "policy.read", "intent.approve"];
const malicious = "[Fake target](javascript:alert(1))\u202e<script>alert(1)</script>";
const question = {
  request_id: "question-1", run_id: run, task_id: task, task_display_key: "P1.1/U1",
  kind: "question", state: "open", revision: 3, audience: "owner",
  blocking_reason: { resolver_role: "owner" }, deadline_at: "2026-11-20T14:00:00Z",
  payload: { text: "Retry 4xx?", options: [{ id: "yes", text: "Retry all" }, { id: "no", text: "Only 5xx" }] },
};
const check = {
  ...question, request_id: "manual-1", kind: "manual_check",
  payload: { check_execution_id: "check-a", check_key: "Dashboard", actor_role: "member" },
};
const intent = {
  intent_id: "intent-1", effect_id: "intent-1", scope_id: run, workspace_id: workspace,
  kind: "git_push", state: "proposed", subject_ref: `run:${run}/attempt:actual`, risk: "high",
  actor_id: testIdentity.principal.principal_id, created_at: "2026-11-20T13:00:00Z", denied_reason: null,
  expires_at: "2026-11-20T18:00:00Z", single_use: false, args_digest: "sha256:original", row_version: 7,
  reason: malicious, approvals: [], normalized_args: {
    target_ref: "refs/heads/reviewed", endpoint: { hostname: "git.example.com", repository_path: "org/repo" },
    refspecs: ["refs/heads/reviewed:refs/heads/reviewed"], force: false,
  },
};

function problem(code: string, status: number, requestId: string, retryable = false) {
  return Response.json({
    code, category: status === 409 ? "conflict" : status === 403 ? "forbidden" : "backend",
    detail: code, request_id: requestId, retryable,
  }, { status, headers: { "Content-Type": "application/problem+json" } });
}

function open(
  handle: (url: URL, init?: RequestInit) => Response | Promise<Response> | undefined,
  grants = permissions,
  { role = "owner", path = `/inbox?project_id=${project}&workspace_id=${workspace}` } = {},
) {
  const posts: { path: string; headers: Headers; body: unknown }[] = [];
  const reads: URL[] = [];
  let feed: ReadableStreamDefaultController<Uint8Array> | undefined;
  let cursor = 40;
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    if (init?.method === "POST") posts.push({ path: url.pathname, headers: new Headers(init.headers), body: JSON.parse(String(init.body)) });
    else reads.push(url);
    const response = await handle(url, init);
    if (response) {
      if (init?.method === "GET" && response.ok) response.headers.set("SKM-Events-Cursor", String(cursor));
      return response;
    }
    switch (url.pathname) {
      case "/api/v1/me":
        return Response.json({
          ...testIdentity, effective_permissions: url.searchParams.has("scope_id") ? grants : [],
          memberships: [{ scope_kind: "workspace", scope_id: workspace as Uuid, role }],
          permissions_by_scope: { [workspace]: grants, [run]: grants },
        });
      case `/api/v1/projects/${project}`: return Response.json({ project_id: project, workspace_id: workspace, title: "Проект" });
      case `/api/v1/workspaces/${workspace}`: return Response.json({ workspace_id: workspace, title: "Пространство" });
      case "/api/v1/execution/detail": return Response.json({ run_id: run, project_id: project, workspace_id: workspace });
      case "/api/v1/inbox": return Response.json({ items: [], next_after: null }, { headers: { "SKM-Events-Cursor": String(cursor) } });
      case "/api/v1/policy/intents": return Response.json({ items: [], next_cursor: null });
      case "/api/v1/events": return new Response(
        new ReadableStream<Uint8Array>({ start(controller) { feed = controller; } }),
        { headers: { "Content-Type": "text/event-stream" } },
      );
      default: return new Response(null, { status: 404 });
    }
  });
  history.replaceState(null, "", path);
  let view = render(<App initialToken="operator" />);
  return {
    posts, reads,
    remount() {
      view.unmount();
      view = render(<App initialToken="operator" />);
    },
    async emit(type: string, payload: object, streamKind = "run", streamId = run) {
      await waitFor(() => expect(feed).toBeDefined());
      cursor += 1;
      const event = { type, workspace_id: workspace, stream_kind: streamKind, stream_id: streamId, payload };
      await act(async () => feed?.enqueue(new TextEncoder().encode(`id: ${cursor}\nevent: message\ndata: ${JSON.stringify(event)}\n\n`)));
    },
  };
}

const page = (items: object[], next_after: string | null = null) => Response.json({ items, next_after });
const policies = (items: object[], next_cursor: string | null = null) => Response.json({ items, next_cursor });

describe("Inbox", () => {
  it("paginates opaque cursors, applies kind and state, switches to run scope, and hands the snapshot cursor to SSE", async () => {
    const user = userEvent.setup();
    let includeCheck = false;
    const app = open(url => {
      if (url.pathname !== "/api/v1/inbox") return;
      if (url.searchParams.has("after")) return page([check]);
      if (includeCheck) return page([question, check]);
      return page([question], "cursor + / ?");
    });
    const decisions = within(await screen.findByRole("region", { name: "Запросы решений" }, { timeout: 3000 }));
    expect(await decisions.findByRole("article", { name: "Retry 4xx?" })).toBeTruthy();
    expect(decisions.getByText("2026-11-20T14:00:00Z")).toBeTruthy();
    expect(decisions.getAllByText("owner")).toHaveLength(2);
    await waitFor(() => expect(app.reads.some(url => url.pathname === "/api/v1/events")).toBe(true));
    const inboxRead = app.reads.findIndex(url => url.pathname === "/api/v1/inbox");
    const streamRead = app.reads.findIndex(url => url.pathname === "/api/v1/events");
    expect(streamRead).toBeGreaterThan(inboxRead);
    expect(app.reads[streamRead]?.searchParams.get("after")).toBe("40");

    await user.click(decisions.getByRole("button", { name: "Далее" }));
    expect(await decisions.findByRole("article", { name: "Dashboard" })).toBeTruthy();
    expect(app.reads.some(url => url.searchParams.get("after") === "cursor + / ?")).toBe(true);
    await user.click(decisions.getByRole("button", { name: "Назад" }));
    await decisions.findByRole("article", { name: "Retry 4xx?" });

    includeCheck = true;
    await app.emit("urn:skm:execution:event:decision-requested:v1", { request_id: check.request_id });
    await decisions.findByRole("article", { name: "Dashboard" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Тип" }), "question");
    await user.selectOptions(screen.getByRole("combobox", { name: "Состояние" }), "answered");
    const scope = screen.getByRole("textbox", { name: "Область" });
    await user.clear(scope);
    await user.type(scope, `run:${run}`);
    await user.click(screen.getByRole("button", { name: "Применить область" }));
    await waitFor(() => expect(app.reads.some(url => url.pathname === "/api/v1/inbox" &&
      url.searchParams.get("scope") === `run:${run}` && url.searchParams.get("kinds") === "question" &&
      url.searchParams.get("states") === "answered" && url.searchParams.get("limit") === "50" &&
      !url.searchParams.has("after"))).toBe(true));
  });

  it("answers with the displayed request revision, updates the open list after continuation, and hides answered actions", async () => {
    const user = userEvent.setup();
    let answered = false;
    const app = open((url, init) => {
      if (url.pathname.endsWith("/answer") && init?.method === "POST") {
        answered = true;
        return Response.json({ request_id: question.request_id, state: "applied", task_status: "ready", next_action_kind: "run_stage" });
      }
      if (url.pathname === "/api/v1/inbox") {
        return url.searchParams.get("states") === "answered" ? page([{ ...question, state: "answered" }])
          : page(answered ? [] : [question]);
      }
    });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Вариант" }), "no");
    await user.type(screen.getByRole("textbox", { name: "Текст ответа" }), "5xx only");
    await user.click(screen.getByRole("button", { name: "Ответить" }));
    await screen.findByRole("heading", { name: "Нет запросов решений" });
    expect(app.posts).toHaveLength(1);
    expect(app.posts[0]).toMatchObject({ path: "/api/v1/decision-requests/question-1/answer", body: {
      request_id: "question-1", expected_revision: 3, answer: { option_id: "no", text: "5xx only" },
    } });
    expect(app.posts[0]?.headers.get("Idempotency-Key")).toMatch(/^web-/u);

    await user.selectOptions(screen.getByRole("combobox", { name: "Состояние" }), "answered");
    await screen.findByRole("article", { name: "Retry 4xx?" });
    expect(screen.queryByRole("button", { name: "Ответить" })).toBeNull();
  });

  it("loads a run inbox before metadata returns and resolves the SSE workspace using inbox.read", async () => {
    let resolveMetadata: (response: Response) => void = () => { throw new Error("Metadata request did not start"); };
    const metadata = new Promise<Response>(resolve => { resolveMetadata = resolve; });
    const app = open(url => {
      if (url.pathname === "/api/v1/execution/detail") return metadata.then(response => response.clone());
      if (url.pathname === "/api/v1/inbox") {
        expect(url.searchParams.get("scope")).toBe(`run:${run}`);
        return page([question]);
      }
      if (url.pathname.startsWith("/api/v1/runs/")) return problem("FORBIDDEN", 403, "run-read-required");
    }, ["inbox.read", "workspace.read"], { path: `/inbox?scope=run:${run}` });
    await screen.findByRole("article", { name: "Retry 4xx?" });
    expect(app.reads.some(url => url.pathname === "/api/v1/events")).toBe(false);
    resolveMetadata(Response.json({
      run_id: run, project_id: project, workspace_id: workspace, plan_id: task, revision_id: finding, row_version: 1,
    }));
    await waitFor(() => expect(app.reads.some(url => url.pathname === "/api/v1/events" &&
      url.searchParams.get("workspace_id") === workspace)).toBe(true));
    expect(app.reads.some(url => url.pathname.startsWith("/api/v1/runs/"))).toBe(false);
    expect(app.reads.some(url => url.pathname.startsWith("/api/v1/policy/"))).toBe(false);
    expect(screen.queryByRole("button", { name: "Ответить" })).toBeNull();
  });

  it("allows an edit only after a definitive rejection and replays the original answer across a page reload", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const app = open(url => {
      if (url.pathname === "/api/v1/inbox") return page([question]);
      if (url.pathname.endsWith("/answer")) {
        attempts += 1;
        if (attempts === 1) return problem("BACKEND_UNAVAILABLE", 503, "unknown-answer", true);
        if (attempts === 2) return problem("SCHEMA_INVALID", 422, "rejected-answer");
        return Response.json({ state: "applied" });
      }
    });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Вариант" }), "no");
    await user.type(screen.getByRole("textbox", { name: "Текст ответа" }), "Original");
    await user.click(screen.getByRole("button", { name: "Ответить" }));
    await screen.findByText("unknown-answer");
    expect(screen.queryByRole("button", { name: "Изменить ответ" })).toBeNull();
    expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Текст ответа" }).closest("fieldset")?.disabled).toBe(true);
    app.remount();
    await user.click(await screen.findByRole("button", { name: "Повторить" }));
    await screen.findByText("rejected-answer");
    expect(app.posts[1]?.body).toEqual(app.posts[0]?.body);
    expect(app.posts[1]?.headers.get("Idempotency-Key")).toBe(app.posts[0]?.headers.get("Idempotency-Key"));
    await user.click(screen.getByRole("button", { name: "Изменить ответ" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Вариант" }), "yes");
    await user.click(screen.getByRole("button", { name: "Ответить" }));
    await waitFor(() => expect(app.posts).toHaveLength(3));
    expect(app.posts[2]?.headers.get("Idempotency-Key")).not.toBe(app.posts[0]?.headers.get("Idempotency-Key"));
  });

  it("hides escalation choices that require additional permissions", async () => {
    open(url => {
      if (url.pathname === "/api/v1/inbox") return page([{
        ...question, kind: "escalation", payload: { code: "WAITING_OWNER", options: ["inspect", "retry_stage", "accept_deviation"] },
      }]);
    }, ["inbox.read", "inbox.answer"]);
    const choices = within(await screen.findByRole("combobox", { name: "Вариант" }));
    expect(choices.getByRole("option", { name: "inspect" })).toBeTruthy();
    expect(choices.queryByRole("option", { name: "retry_stage" })).toBeNull();
    expect(choices.queryByRole("option", { name: "accept_deviation" })).toBeNull();
  });

  it("requires an explicitly approved SHA for every integration mount", async () => {
    const user = userEvent.setup();
    const app = open(url => {
      if (url.pathname === "/api/v1/inbox") return page([{
        ...question, kind: "escalation",
        payload: { code: "INTEGRATION_RECHECK_FAILED", options: ["retry_stage", "fail"], mounts: ["main", "aux\u202e"] },
      }]);
      if (url.pathname.endsWith("/answer")) return Response.json({ state: "applied" });
    });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Вариант" }), "retry_stage");
    const button = screen.getByRole<HTMLButtonElement>("button", { name: "Ответить" });
    await user.type(screen.getByRole("textbox", { name: "SHA для main" }), "a".repeat(40));
    expect(button.disabled).toBe(true);
    await user.type(screen.getByRole("textbox", { name: "SHA для aux\\u202e" }), "b".repeat(64));
    await user.click(button);
    await waitFor(() => expect(app.posts[0]?.body).toMatchObject({
      expected_revision: 3,
      answer: { option_id: "retry_stage", value: { recheck_commits: { main: "a".repeat(40), "aux\u202e": "b".repeat(64) } } },
    }));
  });

  it("retries a manual verdict with the same body and idempotency key", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const app = open(url => {
      if (url.pathname.endsWith("/verdict")) {
        attempts += 1;
        return attempts === 1 ? problem("BACKEND_UNAVAILABLE", 503, "verdict-request", true) : Response.json({});
      }
      if (url.pathname === "/api/v1/inbox") return page(attempts > 1 ? [] : [check]);
    });
    await user.type(await screen.findByRole("textbox", { name: "Комментарий" }), "Three retries");
    await user.click(screen.getByRole("button", { name: "Пройдена" }));
    const error = within(await screen.findByRole("alert"));
    expect(error.getByText("verdict-request")).toBeTruthy();
    await user.click(error.getByRole("button", { name: "Повторить" }));
    await screen.findByRole("heading", { name: "Нет запросов решений" });
    expect(app.posts.map(post => post.body)).toEqual(Array(2).fill({
      check_execution_id: "check-a", verdict: "pass", comment: "Three retries",
    }));
    expect(app.posts[0]?.headers.get("Idempotency-Key")).toMatch(/^web-/u);
    expect(app.posts[1]?.headers.get("Idempotency-Key")).toBe(app.posts[0]?.headers.get("Idempotency-Key"));
  });

  it("filters deviation waits via escalations and uses the bound finding despite a forged label", async () => {
    const user = userEvent.setup();
    const app = open(url => {
      if (url.pathname === "/api/v1/inbox") return page([{
        ...question, request_id: "deviation-1", kind: "escalation",
        payload: { code: "NOT_ACCEPTABLE", refs: { finding_ids: [task, finding] }, finding_label: malicious },
      }]);
      if (url.pathname === "/api/v1/deviations") return Response.json({});
    });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Тип" }), "deviation");
    await user.selectOptions(await screen.findByRole("combobox", { name: "Замечание" }), finding);
    await user.type(await screen.findByRole("textbox", { name: "Причина" }), "Accepted by owner");
    expect(app.reads.some(url => url.pathname === "/api/v1/inbox" && url.searchParams.get("kinds") === "escalation")).toBe(true);
    expect(screen.getByText(finding, { selector: "dd" })).toBeTruthy();
    expect(screen.getByText(malicious.replace("\u202e", "\\u202e"))).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Fake target" })).toBeNull();
    expect(document.querySelector("script")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Принять отклонение" }));
    await waitFor(() => expect(app.posts[0]?.body).toEqual({
      task_id: task, finding_id: finding, scope: "finding", reason: "Accepted by owner",
    }));
  });

  it.each([["APPROVAL_MISMATCH", 403], ["VERSION_CONFLICT", 409]] as const)(
    "keeps the reviewed snapshot through an SSE refresh and %s until explicit reload", async (code, status) => {
      const user = userEvent.setup();
      let current = intent;
      const app = open(url => {
        if (url.pathname === "/api/v1/policy/intents") return policies([intent]);
        if (url.pathname === "/api/v1/policy/intents/intent-1") return Response.json(current);
        if (url.pathname.endsWith("/approve")) return problem(code, status, "approval-request");
      });
      const card = within(await screen.findByRole("article", { name: "Одобрение · git_push" }));
      expect(card.getByText(intent.subject_ref)).toBeTruthy();
      expect(card.getByText(intent.expires_at)).toBeTruthy();
      expect(card.getByText(intent.effect_id)).toBeTruthy();
      expect(card.getByText("false")).toBeTruthy();
      expect(card.getByText(/git\.example\.com/u)).toBeTruthy();
      expect(card.getByText(malicious.replace("\u202e", "\\u202e"))).toBeTruthy();
      expect(card.queryByRole("link", { name: "Fake target" })).toBeNull();
      expect(document.querySelector("script")).toBeNull();

      await user.click(await card.findByRole("button", { name: "Одобрить" }));
      const dialog = within(await screen.findByRole("alertdialog", { name: "Одобрить эффект" }));
      current = { ...intent, args_digest: "sha256:changed", row_version: 8 };
      const detailReads = () => app.reads.filter(url => url.pathname === "/api/v1/policy/intents/intent-1").length;
      const readsBeforeReplay = detailReads();
      await app.emit("urn:skm:policy:event:intent-proposed:v1", { intent_id: intent.intent_id });
      await waitFor(() => expect(detailReads()).toBeGreaterThan(readsBeforeReplay));
      expect(dialog.getByText(intent.args_digest)).toBeTruthy();
      await user.click(dialog.getByRole("button", { name: "Подтвердить одобрение" }));
      const error = within(await card.findByRole("alert"));
      expect(error.getByText(code, { selector: "code" })).toBeTruthy();
      expect(error.getByText("approval-request")).toBeTruthy();
      expect(app.posts).toHaveLength(1);
      expect(app.posts[0]?.body).toEqual({
        intent_id: intent.intent_id, expected_row_version: 7, args_digest: intent.args_digest, single_use: false,
      });
      expect(app.posts[0]?.headers.get("If-Match")).toBe('W/"v7"');
      expect(app.posts[0]?.headers.get("Idempotency-Key")).toMatch(/^web-/u);
      expect(card.getByText(intent.args_digest)).toBeTruthy();
      expect(card.queryByText(current.args_digest)).toBeNull();
      expect(card.queryByRole("button", { name: "Одобрить" })).toBeNull();

      await user.click(card.getByRole("button", { name: "Загрузить текущую версию" }));
      await card.findByText(current.args_digest);
      expect(card.getByRole("button", { name: "Одобрить" })).toBeTruthy();
      expect(app.posts).toHaveLength(1);
    },
  );

  it("paginates proposed policy intents and denies with the reviewed version and a reason", async () => {
    const user = userEvent.setup();
    const app = open(url => {
      if (url.pathname === "/api/v1/policy/intents") return url.searchParams.has("after") ? policies([intent]) : policies([], "policy/+");
      if (url.pathname === "/api/v1/policy/intents/intent-1") return Response.json(intent);
      if (url.pathname.endsWith("/deny")) return Response.json({ state: "denied" });
    });
    const proposed = within(await screen.findByRole("region", { name: "Предложенные эффекты" }));
    await user.click(await proposed.findByRole("button", { name: "Далее" }));
    await user.click(await proposed.findByRole("button", { name: "Отклонить" }));
    const dialog = within(await screen.findByRole("alertdialog", { name: "Отклонить эффект" }));
    await user.type(dialog.getByRole("textbox", { name: "Причина" }), "Wrong destination");
    await user.click(dialog.getByRole("button", { name: "Подтвердить отказ" }));
    await waitFor(() => expect(app.posts[0]).toMatchObject({
      path: "/api/v1/policy/intents/intent-1/deny",
      body: { intent_id: intent.intent_id, expected_row_version: 7, reason: "Wrong destination" },
    }));
    expect(app.posts[0]?.headers.get("If-Match")).toBe('W/"v7"');
    expect(app.posts[0]?.headers.get("Idempotency-Key")).toMatch(/^web-/u);
    expect(app.reads.some(url => url.pathname === "/api/v1/policy/intents" && url.searchParams.get("state") === "proposed" &&
      url.searchParams.get("after") === "policy/+" && url.searchParams.get("workspace_id") === workspace)).toBe(true);
  });

  it("replays an approval with the original request after reloading its projection", async () => {
    const user = userEvent.setup();
    let current = intent;
    let attempts = 0;
    const app = open(url => {
      if (url.pathname === "/api/v1/policy/intents") return policies([intent]);
      if (url.pathname === "/api/v1/policy/intents/intent-1") {
        expect(url.searchParams.get("include_approval_binding")).toBe("true");
        return Response.json(current);
      }
      if (url.pathname.endsWith("/approve")) {
        attempts += 1;
        return attempts === 1 ? problem("BACKEND_UNAVAILABLE", 503, "unknown-approval", true) : Response.json({});
      }
    });
    await user.click(await screen.findByRole("button", { name: "Одобрить" }));
    await user.click(await screen.findByRole("button", { name: "Подтвердить одобрение" }));
    await screen.findByText("unknown-approval");
    current = { ...intent, row_version: 8, args_digest: "sha256:new" };
    await user.click(screen.getByRole("button", { name: "Загрузить текущую версию" }));
    expect(screen.queryByRole("button", { name: "Одобрить" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Отклонить" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    await screen.findByText("Решение записано.");
    expect(app.posts[1]?.body).toEqual(app.posts[0]?.body);
    expect(app.posts[1]?.headers.get("If-Match")).toBe(app.posts[0]?.headers.get("If-Match"));
    expect(app.posts[1]?.headers.get("Idempotency-Key")).toBe(app.posts[0]?.headers.get("Idempotency-Key"));
  });

  it.each(["approved", "denied"])("removes a standalone proposal after the remote intent is %s", async state => {
    let proposed = true;
    const app = open(url => {
      if (url.pathname === "/api/v1/policy/intents") return policies(proposed ? [intent] : []);
      if (url.pathname === "/api/v1/policy/intents/intent-1") return Response.json({ ...intent, state: proposed ? "proposed" : state });
    });
    await screen.findByRole("button", { name: "Отклонить" });
    proposed = false;
    await app.emit(`urn:skm:policy:event:intent-${state}:v1`, { intent_id: intent.intent_id }, "intent", intent.intent_id);
    await screen.findByRole("heading", { name: "Нет предложенных эффектов" });
    expect(screen.queryByRole("button", { name: "Одобрить" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Отклонить" })).toBeNull();
  });

  it("uses the linked execution effect ID and requires the projected approval default", async () => {
    const effectId = "linked-effect";
    const policyView = { ...intent, single_use: undefined };
    open(url => {
      if (url.pathname === "/api/v1/inbox") return page([{
        ...question, request_id: "approval-1", kind: "approval",
        payload: { intent_id: intent.intent_id, refs: { effect_id: effectId } },
      }]);
      if (url.pathname === "/api/v1/policy/intents") return policies([intent]);
      if (url.pathname === "/api/v1/policy/intents/intent-1") return Response.json(policyView);
    });
    const card = within(await screen.findByRole("article", { name: "Одобрение · git_push" }));
    expect(card.getByText(effectId)).toBeTruthy();
    expect(card.getByText("Не указано")).toBeTruthy();
    expect(card.queryByRole("button", { name: "Одобрить" })).toBeNull();
    expect(card.queryByRole("button", { name: "Отклонить" })).toBeNull();
    expect(screen.getAllByRole("article", { name: "Одобрение · git_push" })).toHaveLength(1);
  });

  it("shows review data while hiding actions without scoped permission or a required role", async () => {
    open(url => {
      if (url.pathname === "/api/v1/inbox") return page([
        question, { ...check, payload: { ...check.payload, actor_role: "owner" } },
        { ...check, request_id: "manual-2", payload: { ...check.payload, check_key: "Traces" } },
        { ...check, request_id: "manual-3", payload: { check_execution_id: "check-c", check_key: "Legacy" } },
        { ...question, request_id: "question-2", blocking_reason: null, payload: { text: "Missing resolver" } },
      ]);
      if (url.pathname === "/api/v1/policy/intents") return policies([intent]);
      if (url.pathname === "/api/v1/policy/intents/intent-1") return Response.json(intent);
    }, ["inbox.read", "inbox.answer", "check.verdict", "policy.read"], { role: "member" });
    await screen.findByRole("article", { name: "Retry 4xx?" });
    const protectedCheck = within(await screen.findByRole("article", { name: "Dashboard" }));
    await screen.findByRole("article", { name: "Одобрение · git_push" });
    expect(await within(await screen.findByRole("article", { name: "Traces" })).findByRole("button", { name: "Пройдена" })).toBeTruthy();
    expect(protectedCheck.queryByRole("button", { name: "Пройдена" })).toBeNull();
    expect(protectedCheck.queryByRole("button", { name: "Не пройдена" })).toBeNull();
    expect(within(await screen.findByRole("article", { name: "Legacy" })).queryByRole("button", { name: "Пройдена" })).toBeNull();
    for (const action of ["Одобрить", "Отклонить", "Ответить"]) {
      expect(screen.queryByRole("button", { name: action })).toBeNull();
    }
  });
});
