// @vitest-environment jsdom
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "../../app/App";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import "../../../tests/setup";

const planId = "plan-a";
const revisionId = "revision-picked";
const readinessPath = `/api/v1/plans/${planId}/revisions/${revisionId}/readiness`;
const startPath = `/api/v1/plans/${planId}/runs`;

function fixture(statuses: readonly string[], failFirstStart = false) {
  const sent: { path: string; body: unknown; key: string | null }[] = [];
  let validations = 0;
  let starts = 0;
  stubFetch(async (input, init) => {
    const { pathname } = new URL(String(input), window.location.origin);
    if (init?.method === "POST") {
      sent.push({ path: pathname, body: JSON.parse(String(init.body)), key: new Headers(init.headers).get("Idempotency-Key") });
      if (pathname === readinessPath) {
        const status = statuses[validations++];
        return Response.json({
          status, report_id: `report-${validations}`, estimate: { tasks: 3, token_budget: {
            task_warn_tokens: validations === 1 ? 1250 : 0, task_max_tokens: 4500, run_max_tokens: 0,
          } }, work_policies: {},
          findings: status === "not_ready" ? [{ severity: "blocker", message: "Требуется воркер" }] : [],
        });
      }
      if (pathname === startPath) {
        if (starts++ === 0 && failFirstStart) throw new TypeError("Network failed");
        return Response.json({ run_id: "started-run" }, { status: 201 });
      }
    }
    switch (pathname) {
      case "/api/v1/me": return Response.json({ ...testIdentity, effective_permissions: ["run.start"] });
      case "/api/v1/projects/project-a": return Response.json({ workspace_id: "ws-a", title: "Проект" });
      case "/api/v1/workspaces/ws-a": return Response.json({ workspace_id: "ws-a", title: "Пространство" });
      case "/api/v1/projects/project-a/runs": return Response.json({ items: [], next_after: null });
      case "/api/v1/projects/project-a/plans": return Response.json({
        items: [{ plan_id: planId, alias: "PLAN", title: "План для теста" }], next_cursor: null,
      });
      case `/api/v1/plans/${planId}/revisions`: return Response.json({
        items: [{ revision_id: "revision-current", revision_no: 3 }, { revision_id: revisionId, revision_no: 2 }],
        next_cursor: null,
      });
      default: return new Response(null, { status: 404 });
    }
  });
  history.replaceState(null, "", "/p/project-a/runs");
  render(<App initialToken="valid-token" />);
  return sent;
}

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  const plan = await screen.findByRole("combobox", { name: "План для запуска" }, { timeout: 3000 });
  await screen.findByRole("option", { name: "PLAN · План для теста" });
  await user.selectOptions(plan, planId);
  await screen.findByRole("option", { name: "r2" });
  await user.selectOptions(screen.getByRole("combobox", { name: "Опубликованная ревизия" }), revisionId);
  await user.click(screen.getByRole("button", { name: "Новый запуск" }));
  return within(await screen.findByRole("dialog", { name: "Новый запуск" }));
}

describe("StartRunDialog", () => {
  it("shows blocking readiness findings and prevents start", async () => {
    const sent = fixture(["not_ready"]);
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    await user.type(dialog.getByRole("textbox", { name: "Причина" }), "Проверка");
    await user.click(dialog.getByRole("button", { name: "Проверить готовность" }));
    expect(await dialog.findByText("Требуется воркер")).toBeTruthy();
    expect((dialog.getByRole("button", { name: "Запустить" }) as HTMLButtonElement).disabled).toBe(true);
    expect(sent.map(({ path }) => path)).toEqual([readinessPath]);
  });

  it("revalidates edits and starts the exact selected revision and report, reusing the key on explicit retry", async () => {
    const sent = fixture(["ready", "ready", "ready_with_advisories"], true);
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    const validate = dialog.getByRole("button", { name: "Проверить готовность" });
    const start = dialog.getByRole<HTMLButtonElement>("button", { name: "Запустить" });
    await user.type(dialog.getByRole("textbox", { name: "Причина" }), "Запуск r2");
    await user.click(validate);
    await waitFor(() => expect(start.disabled).toBe(false));
    expect(dialog.getByText("Мягкий порог токенов на задачу").nextElementSibling?.textContent?.trim()).toBe("1250");
    expect(dialog.getByText("Жёсткий лимит токенов на задачу").nextElementSibling?.textContent?.trim()).toBe("4500");
    expect(dialog.getByText("Жёсткий лимит токенов на запуск").nextElementSibling?.textContent?.trim()).toBe("Без лимита");
    await user.type(dialog.getByRole("textbox", { name: "Фазы через запятую" }), "P1, P2");
    expect(start.disabled).toBe(true);
    await user.click(validate);
    await waitFor(() => expect(start.disabled).toBe(false));
    expect(dialog.getByText("Мягкий порог токенов на задачу").nextElementSibling?.textContent?.trim()).toBe("Отключён");
    const overrides = dialog.getByRole("textbox", { name: "Переопределения запуска (JSON)" });
    await user.clear(overrides);
    await user.paste('{"execution.parallel.max_units":2}');
    expect(start.disabled).toBe(true);
    await user.click(validate);
    await waitFor(() => expect(start.disabled).toBe(false));
    await user.click(start);
    await dialog.findByRole("alert");
    expect(sent.filter(item => item.path === startPath)).toHaveLength(1);
    await user.click(start);
    await waitFor(() => expect(location.pathname).toBe("/runs/started-run"));
    const expected = { selection: { phases: ["P1", "P2"] }, overrides: { "execution.parallel.max_units": 2 } };
    expect(sent[2]).toMatchObject({ path: readinessPath, body: expected });
    expect(sent[3]).toMatchObject({
      path: startPath,
      body: { ...expected, revision_id: revisionId, readiness_report_id: "report-3", reason: "Запуск r2" },
      key: expect.stringMatching(/^web-/u),
    });
    expect(sent[4]).toEqual(sent[3]);
  });
});
