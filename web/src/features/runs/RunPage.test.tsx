// @vitest-environment jsdom
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "../../app/App";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";

const run = {
  run_id: "run-a", plan_id: "plan-a", plan_alias: "PLAN", revision_no: 2, kind: "plan", status: "waiting",
  stop_code: "WAITING_MANUAL_CHECK", unmetered: true, health: { health: "blocked", reasons: [] },
  counts_by_status: { manual_pending: 1 }, started_at: null, finished_at: null,
  review_grouping: "none", bundle_digest: "sha256:frozen", work_policy_default: {
    requested: { role_intensity: { reviewer: "heavy" }, verification_intensity: "heavy" },
    effective: { role_intensity: { reviewer: "medium" }, verification_intensity: "medium" },
    role_warn_seconds: { reviewer: 300 }, emergency_role_seconds: { reviewer: 1800 },
  }, autopilot: false, row_version: 7,
};

const tasks = {
  tasks: [
    { task_id: "t-one", display_key: "P1.1", status: "accepted", kind: "unit" },
    { task_id: "t-two", display_key: "P1.2", status: "manual_pending", kind: "unit",
      blocking_reason: { code: "WAITING_MANUAL_CHECK", message: "Проверьте \u202e<script>метку</script>" } },
  ],
  edges: [{ prerequisite_task_id: "t-one", dependent_task_id: "t-two" }],
};
const detail = {
  run_id: "run-a", project_id: "project-a", workspace_id: "ws-a", plan_id: "plan-a", revision_id: "revision-a",
  row_version: 7, workflow: { key: "reviewed-development", version: "1.2.3",
    resource_version_id: "workflow-resource-a", digest: "sha256:workflow" },
};
const task = { task_id: "t-two", display_key: "P1.2", kind: "unit", status: "executing", attempts: [] };
const checkpoint = {
  leased_claim: false, unfinished_stage: false, open_recovery: false,
  changes: [
    { key: "budgets.run.max_tokens", locked: false, ceiling: 7000 },
    { key: "budgets.task.max_tokens", locked: true, ceiling: 6000 },
  ],
};

type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response> | undefined;

function open(path: string, custom?: Handler) {
  const fetch = stubFetch(async (input, init) => {
    const url = new URL(String(input), window.location.origin);
    const response = custom?.(url, init);
    if (response) return response;
    switch (url.pathname) {
      case "/api/v1/me": return Response.json({ ...testIdentity, effective_permissions: ["run.control"] });
      case "/api/v1/projects/project-a": return Response.json({ workspace_id: "ws-a", title: "Проект" });
      case "/api/v1/workspaces/ws-a": return Response.json({ workspace_id: "ws-a", title: "Пространство" });
      case "/api/v1/runs/run-a": return Response.json(run, { headers: { ETag: 'W/"v7"' } });
      case "/api/v1/execution/detail": return Response.json(detail);
      case "/api/v1/runs/run-a/tasks": return Response.json(tasks);
      case "/api/v1/tasks/t-two": return Response.json(task);
      case "/api/v1/tasks/t-two/attempts": return Response.json({ attempts: [] });
      case "/api/v1/runs/run-a/budget":
        return Response.json({ unknown_usage_steps: 2, accounts: [
          { account_id: "account-a", scope: "run", dimension: "tokens", limit: null, spent: "10", reserved: "0", remaining: null },
        ] });
      case "/api/v1/runs/run-a/review-receipt": return Response.json({
        request_id: "review-a", run_id: run.run_id, status: "completed", verdict: "green",
        output_id: "output-a", findings: [], tree_digest: "sha256:tree", base_commit: "base", head_commit: "head",
      });
      default: return new Response(null, { status: 404 });
    }
  });
  history.replaceState(null, "", path);
  render(<App initialToken="valid-token" />);
  return fetch;
}

describe("RunPage", () => {
  it.each([[true, true], [false, true], [true, false]])(
    "gates the report download with exports=%s and run.read=%s", async (enabled, granted) => {
      const fetch = open("/runs/run-a", url => {
        if (url.pathname === "/api/v1/me") return Response.json({
          ...testIdentity, modules: { exports: enabled },
          permissions_by_scope: { "project-a": granted ? ["run.read"] : [] },
        });
      });
      expect(await screen.findByText("reviewed-development @ 1.2.3", {}, { timeout: 3000 })).toBeTruthy();
      expect(!!screen.queryByRole("button", { name: "Export Markdown" })).toBe(enabled && granted);
      expect(fetch.mock.calls.some(([input]) => String(input).includes("/report.md"))).toBe(false);
    },
  );

  it("lays out server dependency edges, renders manual checks as waiting, and shows unknown usage and unlimited budgets", async () => {
    const user = userEvent.setup();
    open("/runs/run-a?project_id=project-a");
    const graph = await screen.findByRole("list", { name: "Зависимости задач" }, { timeout: 3000 });
    expect(await screen.findByText("reviewed-development @ 1.2.3")).toBeTruthy();
    expect(screen.getByText("workflow-resource-a", { selector: "code" })).toBeTruthy();
    expect(screen.getByText("sha256:frozen")).toBeTruthy();
    expect(within(graph).getByRole("button", { name: "P1.2" })).toBeTruthy();
    expect(within(graph).getByText("Зависит от P1.1")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Перейти во входящие" }).getAttribute("href")).toBe("/inbox");
    expect(screen.getByText(/Проверьте \\u202e<script>/u, { selector: "p" })).toBeTruthy();
    expect(screen.queryByText("failed")).toBeNull();
    expect(screen.queryByText("rework_required")).toBeNull();

    await user.click(screen.getByRole("tab", { name: "Бюджет" }));
    const panel = within(await screen.findByRole("tabpanel", { name: "Бюджет" }));
    expect(await panel.findByText("Шаги с неизвестным расходом: 2")).toBeTruthy();
    expect(panel.getByText(/unmetered/u)).toBeTruthy();
    expect(panel.getAllByRole("cell", { name: "Без лимита" })).toHaveLength(2);
    expect(panel.getByRole("cell", { name: "1800" })).toBeTruthy();
    expect(panel.getByRole("cell", { name: "heavy" })).toBeTruthy();
    expect(panel.getByRole("cell", { name: "medium" })).toBeTruthy();
  });

  it("subscribes after the run snapshot cursor and refreshes tasks on a run event", async () => {
    let taskReads = 0;
    let runRead = false;
    sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws-other", projectId: "project-other" }));
    const fetch = open("/runs/run-a", url => {
      if (url.pathname === "/api/v1/runs/run-a") {
        runRead = true;
        return Response.json(run, { headers: { "SKM-Events-Cursor": "42" } });
      }
      if (url.pathname === "/api/v1/runs/run-a/tasks") {
        taskReads += 1;
        return Response.json(taskReads === 1 ? tasks : { ...tasks, tasks: [
          tasks.tasks[0], { ...tasks.tasks[1], status: "accepted", blocking_reason: null },
        ] });
      }
      if (url.searchParams.get("stream") === "run:run-a") {
        expect(runRead).toBe(true);
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(`id: 43\nevent: domain\ndata: ${JSON.stringify({
              stream_kind: "run", stream_id: "run-a", workspace_id: "ws-a", type: "TaskAccepted", payload: { task_id: "t-two" },
            })}\n\n`));
          },
        });
        return new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
      }
    });
    await waitFor(() => expect(taskReads).toBeGreaterThan(1));
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => {
      const params = new URL(String(input), window.location.origin).searchParams;
      return params.get("stream") === "run:run-a" && params.get("after") === "42" && params.get("workspace_id") === "ws-a";
    })).toBe(true));
    expect(fetch.mock.calls.some(([input]) => String(input).includes("workspace_id=ws-other&stream=run"))).toBe(false);
  });

  it("subscribes from a bare task snapshot to its owning run even when another project is saved", async () => {
    sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: "ws-other", projectId: "project-other" }));
    let taskReads = 0;
    const fetch = open("/tasks/t-two", url => {
      if (url.pathname === "/api/v1/tasks/t-two") {
        taskReads += 1;
        return Response.json(task, { headers: { "SKM-Events-Cursor": "51" } });
      }
      if (url.pathname === "/api/v1/execution/detail") {
        expect(url.searchParams.get("task_id")).toBe("t-two");
        return Response.json(detail, { headers: { "SKM-Events-Cursor": "50" } });
      }
      if (url.searchParams.get("stream") === "run:run-a") {
        expect(url.searchParams.get("workspace_id")).toBe("ws-a");
        expect(url.searchParams.get("after")).toBe("50");
        return new Response(new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(`id: 52\nevent: domain\ndata: ${JSON.stringify({
              stream_kind: "run", stream_id: "run-a", workspace_id: "ws-a", type: "TaskReady", payload: { task_id: "t-two" },
            })}\n\n`));
          },
        }), { headers: { "Content-Type": "text/event-stream" } });
      }
    });
    expect((await screen.findByRole("link", { name: "К запуску" })).getAttribute("href")).toBe("/runs/run-a?project_id=project-a");
    await waitFor(() => expect(taskReads).toBeGreaterThan(1));
    const streams = fetch.mock.calls.map(([input]) => new URL(String(input), location.origin).searchParams)
      .filter(params => params.has("stream"));
    expect(streams.map(params => params.get("workspace_id"))).toEqual(["ws-a"]);
  });

  it("renders a recorded soft time warning without changing run status or controls", async () => {
    const now = "2026-11-19T08:00:00Z";
    const history = {
      run_id: run.run_id, through_seq: 12, scanned_through_seq: 12, coverage: "complete", builder_version: 1, next_after: null,
      entries: [{ seq: 12, event_id: "event-12", event_type: "urn:skm:execution:event:monitor-evaluated:v1",
        occurred_at: now, recorded_at: now, coverage: "complete", reason_codes: [], nodes: [], edges: [],
        monitor_evaluation: {
          evaluation_id: "evaluation", monitor_id: "timeout_enforcer", rule_id: "soft_warning", rule_version: "1",
          target_stage_record_id: "stage", fencing_token: 1, config_digest: "sha256:frozen", input_watermark: 11,
          input_coverage: "complete", last_signal_at: null, scheduled_at: now, started_at: now, finished_at: now,
          verdict: "suspected", action: "none", action_request_id: null, recovery_record_id: null,
          reason_code: "SOFT_DURATION_WARNING", config_generation: 1, recovery_mode: null,
          thresholds: [
            { key: "execution.timeout_enforcer.actual_seconds", value: 420 },
            { key: "execution.timeout_enforcer.expected_seconds", value: 300 },
          ],
        },
      }],
    };
    open("/runs/run-a", url => {
      if (url.pathname === "/api/v1/runs/run-a") return Response.json({ ...run, status: "running", stop_code: null });
      if (url.pathname.endsWith("/timeline")) return Response.json({ items: [], next_after: null });
      if (url.pathname.endsWith("/history")) return Response.json(history);
    });
    const user = userEvent.setup();
    const status = await screen.findByRole("heading", { name: /PLAN · r2/u });
    const pause = await screen.findByRole("button", { name: "Приостановить" });
    const cancel = screen.getByRole("button", { name: "Отменить запуск" });
    await user.click(screen.getByRole("tab", { name: "Хронология" }));
    await user.click(screen.getByText("Причинная история"));
    expect(await screen.findByText("Мягкое предупреждение о времени: 420 / 300 с")).toBeTruthy();
    expect(status.textContent).toContain("running");
    expect(screen.getByRole("button", { name: "Приостановить" })).toBe(pause);
    expect(screen.getByRole("button", { name: "Отменить запуск" })).toBe(cancel);
  });

  it("shows frozen task token warnings and hard limits independently", async () => {
    open("/runs/run-a", url => {
      if (url.pathname.endsWith("/budget")) return Response.json({ unknown_usage_steps: 2, accounts: [
        { scope: "task", task_id: "t-one", dimension: "tokens", limit: "900", spent: "750", warn_tokens: 500,
          soft_overrun: { measured_tokens: "600", expected_tokens: 500, partial: true } },
        { scope: "task", task_id: "t-two", dimension: "tokens", limit: null, spent: "0", warn_tokens: 0 },
        { scope: "task", task_id: "t-three", dimension: "tokens", limit: null },
      ] });
    });
    await userEvent.setup().click(await screen.findByRole("tab", { name: "Бюджет" }));
    const row = within(await screen.findByRole("row", { name: /t-one/u }));
    expect(row.getByRole("cell", { name: "900" })).toBeTruthy();
    expect(row.getByText("Мягкое предупреждение о токенах: не менее 600 / 500 токенов")).toBeTruthy();
    expect(within(screen.getByRole("row", { name: /t-two/u })).getByText("Отключён")).toBeTruthy();
    expect(within(screen.getByRole("row", { name: /t-three/u })).getAllByRole("cell", { name: "Неизвестно" }).length).toBeGreaterThan(0);
  });

  it("uses the pinned ETag and row version and leaves a conflict pending until an explicit reload", async () => {
    const controls: RequestInit[] = [];
    const user = userEvent.setup();
    open("/runs/run-a?project_id=project-a", (url, init) => {
      if (url.pathname === "/api/v1/runs/run-a") {
        const version = controls.length ? 8 : 7;
        return Response.json({ ...run, status: "paused", row_version: version }, { headers: { ETag: `W/"v${version}"` } });
      }
      if (url.pathname === "/api/v1/execution/detail") return Response.json({ ...detail, checkpoint });
      if (url.pathname.endsWith("/reconfigure") && init) {
        controls.push(init);
        return Response.json({ code: "VERSION_CONFLICT", category: "conflict", detail: "Новая версия" },
          { status: 409, headers: { "Content-Type": "application/problem+json" } });
      }
    });
    await user.click(await screen.findByRole("button", { name: "Изменить лимиты" }));
    const dialog = within(await screen.findByRole("alertdialog", { name: "Изменить лимиты" }));
    expect(dialog.getByText("budgets.task.max_tokens")).toBeTruthy();
    expect(dialog.queryByRole("spinbutton", { name: "budgets.task.max_tokens" })).toBeNull();
    expect(dialog.queryByRole("spinbutton", { name: "budgets.run.max_usd" })).toBeNull();
    await user.type(dialog.getByRole("spinbutton", { name: "budgets.run.max_tokens" }), "5000");
    await user.type(dialog.getByRole("textbox", { name: "Причина" }), "Новый лимит");
    await user.click(dialog.getByRole("button", { name: "Изменить лимиты" }));
    const reload = await dialog.findByRole("button", { name: "Загрузить текущую версию" });
    expect(controls).toHaveLength(1);
    expect(new Headers(controls[0]?.headers).get("If-Match")).toBe('W/"v7"');
    expect(new Headers(controls[0]?.headers).get("Idempotency-Key")).toMatch(/^web-/u);
    expect(JSON.parse(String(controls[0]?.body))).toEqual({
      expected_row_version: 7, reason: "Новый лимит", changes: { "budgets.run.max_tokens": 5000 },
    });
    await user.click(reload);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(controls).toHaveLength(1);
  });

  it("shows all current checkpoint blockers before accepting changes", async () => {
    open("/runs/run-a", url => {
      if (url.pathname === "/api/v1/runs/run-a") return Response.json({ ...run, status: "paused" });
      if (url.pathname === "/api/v1/execution/detail") return Response.json({ ...detail, checkpoint: {
        ...checkpoint, leased_claim: true, unfinished_stage: true, open_recovery: true,
      } });
    });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Изменить лимиты" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Изменить лимиты" }));
    for (const label of ["Активная аренда", "Незавершённая стадия", "Открытое восстановление"]) {
      expect(dialog.getByText(label).nextElementSibling?.textContent?.trim()).toBe("Да");
    }
    expect(dialog.queryByRole("spinbutton")).toBeNull();
    expect(dialog.getByText(/Заблокировано настройками/u)).toBeTruthy();
  });

  it.each(["review_request", "readiness_audit"])("renders a %s run on the run route", async kind => {
    open("/runs/run-a", url => {
      if (url.pathname === "/api/v1/runs/run-a") return Response.json({ ...run, kind });
    });
    expect(await screen.findByText(kind)).toBeTruthy();
    if (kind === "review_request") expect(await screen.findByText("sha256:tree")).toBeTruthy();
  });

  it("shows live events on the attempt route using the owning project's setting", async () => {
    const setting = "ui.runs.live_stream";
    open("/attempts/attempt-a", url => {
      if (url.pathname === "/api/v1/attempts/attempt-a") return Response.json({
        attempt_id: "attempt-a", attempt_no: 1, state: "running", finished_at: null, stages: [], steps: [],
        outputs: [], checks: [], reviews: [], findings: [], effects: [], recoveries: [],
      });
      if (url.pathname === "/api/v1/config/effective" && url.searchParams.get("keys") === setting) {
        expect(url.searchParams.get("scope")).toBe("project:project-a");
        return Response.json({ keys: [{ key: setting, value: true }] });
      }
      if (url.pathname === "/api/v1/attempts/attempt-a/live") {
        const delta = { type: "text_delta", channel: "stdout", text: "Вывод выполняемой попытки" };
        return new Response(`id: 1\nevent: text_delta\ndata: ${JSON.stringify(delta)}\n\nevent: end\ndata: {}\n\n`,
          { headers: { "Content-Type": "text/event-stream" } });
      }
    });
    const live = within(await screen.findByRole("region", { name: "Прямой эфир попытки" }));
    expect(await live.findByText(/Вывод выполняемой попытки/u)).toBeTruthy();
  });

  it.each([["ws-a", "project", "project-a"], ["ws-b", "workspace", "ws-a"]])(
    "closes the live feed on settings changes with %s selected", async (selected, level, scopeId) => {
      const setting = "ui.runs.live_stream";
      const crossWorkspace = selected !== detail.workspace_id;
      const shellCursor = crossWorkspace ? 500 : 10;
      let enabled = true;
      let reads = 0;
      let settingsFeed: ReadableStreamDefaultController<Uint8Array> | undefined;
      let closed = false;
      let shellConnected!: () => void;
      const shellReady = new Promise<void>(resolve => { shellConnected = resolve; });
      sessionStorage.setItem("skm.scope", JSON.stringify({ workspaceId: selected, projectId: "stored-project" }));

      open("/attempts/attempt-a", (url) => {
        if (url.pathname === `/api/v1/workspaces/${selected}`) return Response.json({ workspace_id: selected },
          { headers: { "SKM-Events-Cursor": String(shellCursor) } });
        if (url.pathname === "/api/v1/events") {
          const workspace = url.searchParams.get("workspace_id");
          return new Response(new ReadableStream<Uint8Array>({ start(controller) {
            if (workspace === selected) shellConnected();
            if (workspace === detail.workspace_id) {
              expect(url.searchParams.get("after")).toBe(crossWorkspace ? "14" : "10");
              settingsFeed = controller;
            }
          } }), { headers: { "Content-Type": "text/event-stream" } });
        }
        if (url.pathname === "/api/v1/execution/detail") return shellReady.then(() => Response.json(detail));
        if (url.pathname === "/api/v1/attempts/attempt-a") return Response.json({
          attempt_id: "attempt-a", attempt_no: 1, state: "running", finished_at: null, stages: [], steps: [],
          outputs: [], checks: [], reviews: [], findings: [], effects: [], recoveries: [],
        });
        if (url.pathname === "/api/v1/config/effective" && url.searchParams.get("keys") === setting) {
          expect(url.searchParams.get("scope")).toBe("project:project-a");
          if (++reads > 2) throw Error("Unexpected repeat of the live settings GET");
          return Response.json({ keys: [{ key: setting, value: enabled }] },
            { headers: { "SKM-Events-Cursor": enabled ? "14" : "15" } });
        }
        if (url.pathname === "/api/v1/attempts/attempt-a/live") return new Response(new ReadableStream({
          cancel() { closed = true; },
        }), { headers: { "Content-Type": "text/event-stream" } });
      });

      expect(await screen.findByText("В эфире")).toBeTruthy();
      expect(reads).toBe(1);
      enabled = false;
      const event = {
        type: "urn:skm:settings:event:config-changed:v1", workspace_id: "ws-a", stream_kind: "config", stream_id: scopeId,
        payload: { scope: { level, scope_id: scopeId }, keys: [setting] },
      };
      await act(async () => settingsFeed!.enqueue(new TextEncoder().encode(`id: 15\ndata: ${JSON.stringify(event)}\n\n`)));
      await waitFor(() => expect(closed).toBe(true));
      expect(reads).toBe(2);
      expect(screen.queryByRole("region", { name: "Прямой эфир попытки" })).toBeNull();
    },
  );

  it("shows step metadata and opens saved transcript bytes only on request", async () => {
    const fetch = open("/attempts/attempt-a", url => {
      if (url.pathname === "/api/v1/attempts/attempt-a") return Response.json({
        attempt_id: "attempt-a", attempt_no: 1, state: "completed", finished_at: "2026-11-19T08:00:00Z", stages: [],
        steps: [{ step_id: "step-a", role: "executor", purpose: "execute", state: "completed" }],
        outputs: [], checks: [{ check_execution_id: "check-a", state: "manual_pending" }], reviews: [],
        findings: [], effects: [], recoveries: [],
      });
      if (url.pathname === "/api/v1/steps/step-a") return Response.json({
        step_id: "step-a", role: "executor", model: "resolved-model", runtime_id: "provider<svg>\u202e",
        route_snapshot: { requested: { runtime_id: "requested-runtime", model: "requested-model" } },
        runtime_observation: {
          binding: { provider_reported_model: null }, timing: { duration_ms: 0 },
          capture: { coverage: "partial", truncated: true, gaps: ["capture_gap"], parser_flags: [] },
          tools: { coverage: "unavailable", observed_calls: null },
        },
        usage: { status: "unknown", input_tokens: null, subagents: { used: null, disclosed: false } },
        repairs: [], schema_errors: [], payload_visibility: "available", transcript_file_version_id: "transcript-a",
      });
      if (url.pathname === "/api/v1/file-versions/transcript-a/content") return new Response("Сохранённый вывод");
    });
    const user = userEvent.setup();
    expect(await screen.findByRole("link", { name: "Перейти во входящие" })).toBeTruthy();
    await user.click(await screen.findByText(/executor · execute/u));
    expect(await screen.findByRole("heading", { name: "Привязка модели" })).toBeTruthy();
    expect(screen.getByText("requested-model")).toBeTruthy();
    expect(screen.getByText("resolved-model")).toBeTruthy();
    expect(screen.getByText("provider<svg>\\u202e")).toBeTruthy();
    for (const label of ["Модель по сообщению провайдера", "Входные токены", "Наблюдаемые вызовы"]) {
      expect(screen.getByText(label).nextElementSibling?.textContent?.trim()).toBe("Неизвестно");
    }
    expect(screen.getByRole("button", { name: "Скачать транскрипт" })).toBeTruthy();
    const openTranscript = await screen.findByRole("button", { name: "Открыть транскрипт шага step-a" });
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/attempts/attempt-a/live"))).toBe(false);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/content"))).toBe(false);
    await user.click(openTranscript);
    expect(await screen.findByText("Сохранённый вывод", { selector: "code" })).toBeTruthy();
  });

  it("binds checks, evidence, and recurring findings to the exact outputs and review rounds", async () => {
    const fetch = open("/attempts/attempt-a", url => {
      if (url.pathname === "/api/v1/attempts/attempt-a") return Response.json({
        attempt_id: "attempt-a", attempt_no: 1, state: "completed", stages: [], steps: [], effects: [], recoveries: [],
        outputs: [{ output_id: "output-one" }, { output_id: "output-two" }],
        checks: [
          { check_execution_id: "check-one", check_key: "V1 first", output_id: "output-one", round_no: 1, state: "failed",
            evidence_refs: [{ file_version_id: "stderr-one", role: "stderr" }] },
          { check_execution_id: "check-two", check_key: "V1 second", output_id: "output-two", round_no: 2, state: "passed",
            evidence_refs: [{ file_version_id: "stdout-two", role: "stdout" }] },
        ],
        reviews: [
          { review_id: "review-one", round_no: 1, output_id: "output-one", profile_key: "reviewer", verdict: "red" },
          { review_id: "review-two", round_no: 2, output_id: "output-two", profile_key: "reviewer", verdict: "red",
            evidence_refs: [{ file_version_id: "review-proof-two", role: "report" }] },
        ],
        findings: [
          { finding_id: "finding-one", review_id: "review-one", finding_key: "fk-1234567890abcdef",
            first_seen_review_id: "review-one", message: "Original finding", severity: "major", state: "open" },
          { finding_id: "finding-two", review_id: "review-two", finding_key: "fk-1234567890abcdef",
            first_seen_review_id: "review-one", message: "Still present", severity: "major", state: "open" },
        ],
      });
    });
    const checks = within((await screen.findByRole("heading", { name: "Проверки" })).closest("section")!);
    const first = within(checks.getByText("check-one").closest("li")!);
    const second = within(checks.getByText("check-two").closest("li")!);
    expect(first.getByText("output-one")).toBeTruthy();
    expect(first.getByText("stderr-one")).toBeTruthy();
    expect(first.queryByText("stdout-two")).toBeNull();
    expect(second.getByText("output-two")).toBeTruthy();
    expect(second.getByText("stdout-two")).toBeTruthy();
    expect(second.queryByText("stderr-one")).toBeNull();

    const reviews = within(screen.getByRole("heading", { name: "Ревью" }).closest("section")!);
    const roundOne = within(reviews.getByText(/Раунд 1 ·/u).closest("li")!);
    const roundTwo = within(reviews.getByText(/Раунд 2 ·/u).closest("li")!);
    expect(roundOne.getByText("output-one")).toBeTruthy();
    expect(roundOne.getByText("fk-1234567890abcdef")).toBeTruthy();
    expect(roundOne.getByText("Original finding")).toBeTruthy();
    expect(roundOne.queryByText("Still present")).toBeNull();
    expect(roundTwo.getByText("output-two")).toBeTruthy();
    expect(roundTwo.getByText("fk-1234567890abcdef")).toBeTruthy();
    expect(roundTwo.getByText("Still present")).toBeTruthy();
    expect(roundTwo.getByText("review-proof-two")).toBeTruthy();
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/content"))).toBe(false);
  });

  it("reads the project manifest and fetches captured block text only when requested", async () => {
    const path = "/api/v1/projects/project-a/context-manifests/manifest-a";
    const fetch = open("/steps/step-a/context?project_id=project-a", url => {
      if (url.pathname === "/api/v1/steps/step-a") return Response.json({ context_manifest_id: "manifest-a" });
      if (url.pathname === path) return Response.json({
        state: "finalized", route: {}, mode: null,
        rows: [{ pos: 0, included: true, block_type: "history", source: "source-a", tokens: 0 }],
      });
      if (url.pathname === path + "/text" && url.searchParams.get("position") === "0") {
        return Response.json({ available: true, text: "<svg onload=alert(1)>\u202e", prompt_file_version_id: null });
      }
    });
    const button = await screen.findByRole("button", { name: "Текст блока 0" });
    expect(fetch.mock.calls.some(([url]) => String(url).includes(path + "/text"))).toBe(false);
    await userEvent.setup().click(button);
    expect(await screen.findByText("<svg onload=alert(1)>\\u202e")).toBeTruthy();
    expect(document.querySelector("svg[onload]")).toBeNull();
  });

});

describe("TaskPage restart", () => {
  it.each([
    { status: "executing", eligible: true, requiresOverride: false, deviation: false, shown: true },
    { status: "reviewing", eligible: true, requiresOverride: true, deviation: true, shown: true },
    { status: "checking", eligible: true, requiresOverride: true, deviation: false, shown: false },
    { status: "failed", eligible: false, requiresOverride: false, deviation: true, shown: false },
    { status: "manual_pending", eligible: false, requiresOverride: false, deviation: false, shown: false },
  ])("checks server restart eligibility and permission for $status ($deviation)", async ({
    status, eligible, requiresOverride, deviation, shown,
  }) => {
    const commands: unknown[] = [];
    open("/tasks/t-two", (url, init) => {
      if (url.pathname === "/api/v1/me") return Response.json({
        ...testIdentity, permissions_by_scope: { "run-a": deviation ? ["run.control", "deviation.accept"] : ["run.control"] },
      });
      if (url.pathname === "/api/v1/tasks/t-two") return Response.json({ ...task, status });
      if (url.pathname === "/api/v1/execution/detail") return Response.json({
        ...detail, restart: { eligible, requires_attempts_override: requiresOverride },
      });
      if (url.pathname.endsWith("/restart")) {
        commands.push(JSON.parse(String(init?.body)));
        return Response.json({ task_id: task.task_id, status: "ready" });
      }
    });
    await screen.findByRole("link", { name: "К запуску" });
    const user = userEvent.setup();
    if (status === "manual_pending") expect(screen.getByRole("link", { name: "Перейти во входящие" })).toBeTruthy();
    if (!shown) {
      expect(screen.queryByRole("button", { name: "Перезапустить задачу" })).toBeNull();
      expect(commands).toEqual([]);
      return;
    }
    await user.click(await screen.findByRole("button", { name: "Перезапустить задачу" }));
    const dialog = within(await screen.findByRole("alertdialog", { name: "Перезапустить задачу" }));
    const override = dialog.queryByRole("checkbox", { name: "Поднять лимит попыток" });
    if (override) await user.click(override);
    expect(Boolean(override)).toBe(requiresOverride);
    await user.type(dialog.getByRole("textbox", { name: "Причина" }), "Новая попытка");
    await user.click(dialog.getByRole("button", { name: "Перезапустить задачу" }));
    await waitFor(() => expect(commands).toEqual([{ reason: "Новая попытка", ...(requiresOverride && { raise_attempts_limit: true }) }]));
  });
});

const livePath = "/api/v1/runs/run-a/tasks/t-two";
const liveSnapshot = {
  row_version: 7, assignment_id: "assignment-a", fencing_token: 3, active_step_id: "step-a",
  cancellation_requested: false, pending_controls: [],
  steps: [{ step_id: "step-a", role: "executor", state: "started", coverage: "unavailable" }],
  selected_step_id: "step-a",
  tool_calls: [{ call_id: "call-a", tool: "<file.read>", duration_ms: null, coverage: "partial" }],
  next_call_id: null,
};

describe("run live control", () => {
  it("loads the journal on demand and shows partial coverage and unknown durations", async () => {
    const user = userEvent.setup();
    const fetch = open("/runs/run-a", url => {
      if (url.pathname === livePath + "/live-control") return Response.json(liveSnapshot);
    });
    const tab = await screen.findByRole("tab", { name: "Управление и инструменты" }, { timeout: 3000 });
    expect(fetch.mock.calls.some(([input]) => String(input).includes("/live-control"))).toBe(false);
    await user.click(tab);
    const panel = within(await screen.findByRole("tabpanel", { name: "Управление и инструменты" }));
    const row = within(await panel.findByRole("row", { name: /call-a/u }));
    expect(row.getByRole("cell", { name: "<file.read>" })).toBeTruthy();
    expect(row.getByRole("cell", { name: "Неизвестно" })).toBeTruthy();
    expect(panel.getByText("Покрытие наблюдений: Частичное")).toBeTruthy();
  });

  it.each([
    ["Изменить маршрут", "/reroute", { "Среда выполнения": "fake", "Модель": "model-b" },
      { runtime_id: "fake", model: "model-b" }],
    ["Заменить профиль агента", "/override-actor", { "Ключ профиля": "executor" }, { actor_profile: "executor" }],
    ["Добавить инструкции", "/steer", { "Инструкции": "Use the fixture" }, { instructions: "Use the fixture" }],
    ["Прервать шаг", "/abort-step", {}, {}],
  ] as const)("submits %s with the displayed ownership and version", async (label, path, fields, changes) => {
    const user = userEvent.setup();
    let submitted: RequestInit | undefined;
    open("/runs/run-a", (url, init) => {
      if (url.pathname === livePath + "/live-control") return Response.json(liveSnapshot);
      if (url.pathname === livePath + path) {
        submitted = init;
        return Response.json({ gate_id: "gate-a", row_version: 8, effective: "next_step" });
      }
    });
    await user.click(await screen.findByRole("tab", { name: "Управление и инструменты" }));
    await user.click(await screen.findByRole("button", { name: label }));
    const dialog = within(await screen.findByRole("alertdialog", { name: label }));
    for (const [name, input] of Object.entries(fields)) await user.type(dialog.getByLabelText(name), input);
    await user.type(dialog.getByLabelText("Причина"), "Operator request");
    await user.click(dialog.getByRole("button", { name: label }));
    await waitFor(() => expect(submitted).toBeDefined());
    expect(new Headers(submitted?.headers).get("If-Match")).toBe('W/"v7"');
    expect(JSON.parse(String(submitted?.body))).toEqual({
      expected_assignment_id: "assignment-a", expected_fencing_token: 3, expected_step_id: "step-a",
      reason: "Operator request", ...changes,
    });
  });

  it("gates mutations by run.control and keeps journal reads available", async () => {
    const user = userEvent.setup();
    open("/runs/run-a", url => {
      if (url.pathname === "/api/v1/me") return Response.json({
        ...testIdentity, effective_permissions: ["run.read"], permissions_by_scope: {},
      });
      if (url.pathname === livePath + "/live-control") return Response.json({
        ...liveSnapshot, cancellation_requested: true,
      });
    });
    await user.click(await screen.findByRole("tab", { name: "Управление и инструменты" }));
    expect(await screen.findByText("Запрошена остановка шага.")).toBeTruthy();
    for (const name of ["Изменить маршрут", "Заменить профиль агента", "Добавить инструкции", "Прервать шаг"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
  });
});
