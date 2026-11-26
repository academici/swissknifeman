import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { stubFetch, testIdentity } from "../../../tests/fakeTransport";
import { App } from "../../app/App";

const reportId = "01900000-0000-7000-8000-000000000001";
const planPath = "/api/v1/plans/plan";
const revisionPath = planPath + "/revisions/head";

function showPlan(permissions: string[], handle: (url: URL, init?: RequestInit) => Response | undefined) {
  stubFetch(async (input, init) => {
    const url = new URL(String(input), location.origin);
    const response = handle(url, init);
    if (response) return response;
    switch (url.pathname) {
      case "/api/v1/me": return Response.json({ ...testIdentity, permissions_by_scope: { plan: permissions } });
      case planPath: return Response.json({ plan_id: "plan", alias: "PLAN1", title: "Title",
        current_revision_id: "head", current_revision_no: 1, open_drafts: 0, lifecycle_state: "active" });
      case planPath + "/revisions": return Response.json({ items: [], next_cursor: null });
      case planPath + "/entities": return Response.json({ items: [], next_cursor: null });
      case revisionPath: return Response.json({ tree: { phases: [] } });
      default: throw new Error(url.pathname);
    }
  });
  history.replaceState(null, "", "/plans/plan");
  render(<App initialToken="test" />);
}

it("loads simulation on demand and distinguishes missing metrics from a free tariff", async () => {
  const rates: (string | null)[] = [];
  showPlan(["plan.read"], url => {
    if (url.pathname !== revisionPath + "/simulate") return undefined;
    const rate = url.searchParams.get("tokens_per_second");
    rates.push(rate);
    return Response.json({ basis: "heuristic", task_count: 1, tokens: { min: 128, max: 512 },
      cost_usd_micros: rate ? { min: 0, max: 0 } : null,
      duration_seconds: rate ? { min: 2, max: 11 } : null, tokens_per_second: rate ? Number(rate) : null });
  });
  const tab = await screen.findByRole("tab", { name: "Симуляция" });
  expect(rates).toEqual([]);
  await userEvent.click(tab);
  const panel = within(await screen.findByRole("region", { name: "Симуляция плана" }));
  await panel.findByText("heuristic");
  expect(panel.getByText("128–512")).toBeTruthy();
  expect(panel.getAllByText("unknown")).toHaveLength(2);
  await userEvent.type(panel.getByRole("spinbutton"), "50");
  await userEvent.click(panel.getByRole("button", { name: "Рассчитать" }));
  expect(await panel.findByText("0–0")).toBeTruthy();
  expect(panel.getByText("2–11")).toBeTruthy();
  expect(panel.queryByText("unknown")).toBeNull();
  expect(rates).toEqual([null, "50"]);
});

it("validates and signs a revision, then shows its persisted Visa", async () => {
  let signed = false;
  const writes: { path: string; body: unknown; idempotency: string | null }[] = [];
  const signature = { visa_id: "visa-1", revision_id: "head", readiness_report_id: reportId, signed_at: "2026-01-01" };
  showPlan(["plan.read", "plan.approve", "run.start"], (url, init) => {
    if (url.pathname === revisionPath + "/visa") return Response.json({ latest_signature: signed ? signature : null });
    if (init?.method !== "POST") return undefined;
    writes.push({ path: url.pathname, body: JSON.parse(String(init.body)),
      idempotency: new Headers(init.headers).get("Idempotency-Key") });
    if (url.pathname === revisionPath + "/readiness") {
      return Response.json({ report_id: reportId, status: "ready_with_advisories", findings: [{ message: "Advisory" }] }, { status: 201 });
    }
    if (url.pathname === planPath + "/revision-visas") {
      signed = true;
      return Response.json(signature, { status: 201 });
    }
    return undefined;
  });
  await userEvent.click(await screen.findByRole("tab", { name: "PlanVisa" }));
  const panel = within(await screen.findByRole("region", { name: "PlanVisa" }));
  await panel.findByText("Подписей пока нет.");
  const sign = panel.getByRole<HTMLButtonElement>("button", { name: "Подписать визу" });
  expect(sign.disabled).toBe(true);
  await userEvent.click(panel.getByRole("button", { name: "Проверить готовность ревизии" }));
  await panel.findByText("Advisory");
  expect(sign.disabled).toBe(true);
  await userEvent.type(panel.getByRole("textbox", { name: "Причина одобрения" }), "Reviewed plan");
  await userEvent.click(sign);
  expect(await panel.findByText("visa-1")).toBeTruthy();
  expect(writes.map(({ path, body }) => ({ path, body }))).toEqual([
    { path: revisionPath + "/readiness", body: { mode: "full" } },
    { path: planPath + "/revision-visas", body: { readiness_report_id: reportId, reason: "Reviewed plan" } },
  ]);
  expect(writes.every(write => write.idempotency?.startsWith("web-"))).toBe(true);
});

it("shows Visa status without signing controls for a reader", async () => {
  showPlan(["plan.read"], url => url.pathname === revisionPath + "/visa"
    ? Response.json({ latest_signature: null }) : undefined);
  await userEvent.click(await screen.findByRole("tab", { name: "PlanVisa" }));
  await screen.findByText("Подписей пока нет.");
  expect(screen.queryByRole("button", { name: "Подписать визу" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Проверить готовность ревизии" })).toBeNull();
});

it("refuses to sign a readiness report for a different revision", async () => {
  showPlan(["plan.read", "plan.approve"], url => {
    if (url.pathname === revisionPath + "/visa") return Response.json({ latest_signature: null });
    if (url.pathname === "/api/v1/readiness-reports/" + reportId) return Response.json({
      report: { plan_id: "plan", revision_id: "previous" }, effective_status: "ready",
    });
    return undefined;
  });
  await userEvent.click(await screen.findByRole("tab", { name: "PlanVisa" }));
  const panel = within(await screen.findByRole("region", { name: "PlanVisa" }));
  await userEvent.type(panel.getByRole("textbox", { name: "ID отчёта о готовности" }), reportId);
  await userEvent.click(panel.getByRole("button", { name: "Загрузить отчёт" }));
  await panel.findByText("Отчёт относится к другой ревизии.");
  await userEvent.type(panel.getByRole("textbox", { name: "Причина одобрения" }), "Wrong revision");
  expect(panel.getByRole<HTMLButtonElement>("button", { name: "Подписать визу" }).disabled).toBe(true);
});
